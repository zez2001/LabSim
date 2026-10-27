"""Read-only π0.5 input audit, including an offline deployed-processor preflight.

Run this module in the existing policy Python, not Isaac Python. The preflight
loads configuration, normalization statistics and the cached tokenizer only;
no model weights, CUDA device, RPC service or network download are needed.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import threading
from urllib.parse import urlparse
from unittest.mock import patch

import numpy as np


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def array_spec(value):
    value = np.asarray(value)
    return dict(shape=list(value.shape), dtype=str(value.dtype),
                sha256=hashlib.sha256(value.tobytes()).hexdigest())


def source_identity(value):
    source = Path(inspect.getfile(value)).resolve()
    return dict(path=str(source), sha256=sha256_file(source))


def token_audit(transform, prompt, state, actual_ids, actual_mask):
    """Check installed tokenizer output against the effective transformed input.

    The token sequence below is a reconstruction of the installed
    PaligemmaTokenizer formatting. Equality with the *actual* transform result
    is recorded, so a future tokenizer implementation change cannot silently be
    reported as verified. This function does not alter its arguments.
    """
    tokenizer = transform.tokenizer
    sp = tokenizer._tokenizer
    cleaned = str(prompt).strip().replace('_', ' ').replace('\n', ' ')
    discrete = bool(transform.discrete_state_input)
    if discrete:
        state_bins = np.digitize(state, bins=np.linspace(-1, 1, 257)[:-1]) - 1
        formatted = f"Task: {cleaned}, State: {' '.join(map(str, state_bins))};\nAction: "
        raw = sp.encode(formatted, add_bos=True)
        formatting = 'Task: {cleaned}, State: {quantile-normalized state bins};\\nAction: '
    else:
        formatted = cleaned
        raw = sp.encode(cleaned, add_bos=True) + sp.encode('\n')
        formatting = 'encode(cleaned, add_bos=True) + encode(newline); no Task/State/Action prefix'
    limit = int(tokenizer._max_len)
    kept = raw[:limit]
    expected_ids = kept + [0] * max(0, limit - len(kept))
    expected_mask = [True] * len(kept) + [False] * max(0, limit - len(kept))
    ids = np.asarray(actual_ids).tolist()
    mask = np.asarray(actual_mask, dtype=bool).tolist()
    active = [int(t) for t, selected in zip(ids, mask) if selected]
    return dict(
        task_text=str(prompt), task_text_sha256=hashlib.sha256(str(prompt).encode()).hexdigest(),
        cleaned_text=cleaned, formatted_text=formatted, formatting=formatting,
        discrete_state_input=discrete, raw_token_count=len(raw), model_max_tokens=limit,
        truncated=len(raw) > limit, discarded_token_count=max(0, len(raw) - limit),
        raw_token_ids=list(map(int, raw)), effective_token_ids=ids,
        effective_token_mask=mask, active_token_count=sum(mask),
        effective_tokens_sha256=hashlib.sha256(np.asarray(actual_ids).tobytes()).hexdigest(),
        effective_token_array=array_spec(actual_ids), mask_array=array_spec(actual_mask),
        effective_decoded=sp.decode(active), discarded_decoded=sp.decode(raw[limit:]),
        bos_id=int(sp.bos_id()), eos_id=int(sp.eos_id()), pad_id=int(sp.pad_id()),
        add_bos=True, add_eos=False, separate_newline_ids=list(map(int, sp.encode('\n'))) if not discrete else [],
        eos_present_in_effective=int(sp.eos_id()) in active,
        output_matches_installed_formatting=(ids == expected_ids and mask == expected_mask),
        tokenizer_class=type(tokenizer).__module__ + '.' + type(tokenizer).__name__,
        tokenizer_source=source_identity(type(tokenizer)),
        sentencepiece_model_sha256=hashlib.sha256(sp.serialized_model_proto()).hexdigest(),
        tokenizer_vocabulary_size=int(sp.vocab_size()),
        attention_semantics='True marks valid language tokens; false padding excluded. The installed PI0Pytorch prefix uses bidirectional image/language attention.',
    )


def find_token_transform(processor):
    candidates = [t for t in getattr(processor, 'transforms', ())
                  if type(t).__name__ == 'TokenizePrompt' and hasattr(t, 'tokenizer')]
    if len(candidates) != 1:
        raise ValueError('Expected exactly one installed TokenizePrompt transform')
    return candidates[0]


class AuditedInputTransform:
    """Call the deployed processor exactly once, then inspect its unchanged output."""
    def __init__(self, processor, output, request_index):
        self.processor = processor
        self.token_transform = find_token_transform(processor)
        self.output = Path(output)
        self.request_index = request_index
        self._lock = threading.Lock()

    def __call__(self, sample):
        prompt = str(sample['prompt'])
        state_width = np.asarray(sample['observation/state']).shape[-1]
        result = self.processor(sample)
        report = token_audit(self.token_transform, prompt, result['state'][:state_width],
                             result['tokenized_prompt'], result['tokenized_prompt_mask'])
        report.update(schema='labsim.pi05.effective_input_audit.v1',
                      request_index=int(self.request_index()),
                      task_text_source='same request_index in inference.jsonl task_descriptions',
                      image={key: array_spec(value) for key, value in result['image'].items()},
                      image_mask={key: bool(value) for key, value in result['image_mask'].items()},
                      audit_scope='actual inherited input transform, before tensor batching/device transfer')
        with self._lock, self.output.open('a', encoding='utf-8') as destination:
            destination.write(json.dumps(report, ensure_ascii=False, allow_nan=False) + '\n')
        return result


@contextlib.contextmanager
def cached_downloads_only():
    """Allow existing local/cache paths; deny every download/cache mutation."""
    import openpi.shared.download as download
    resolved = []

    def local_only(url, **kwargs):
        parsed = urlparse(str(url))
        if not parsed.scheme:
            path = Path(url).expanduser()
        else:
            root = Path(os.environ.get('OPENPI_DATA_HOME', '~/.cache/openpi')).expanduser()
            path = root / parsed.netloc / parsed.path.lstrip('/')
        if kwargs.get('force_download') or not path.exists():
            raise FileNotFoundError('Offline input audit requires the existing cached file: ' + str(path))
        path = path.resolve()
        resolved.append(str(path))
        return path

    with patch.object(download, 'maybe_download', local_only):
        yield resolved


def deployed_processor(model_path):
    """Build the same installed preprocessing chain without constructing a model."""
    import openpi.transforms as transforms
    from openpi.training import checkpoints
    # Importing RPent's server selects the same optional RLinf source path as
    # the real service. Its model constructor is never called here.
    from rpent.robots.components.pi05_vla_server import PI05_EMBODIMENTS, build_model_cfg
    from rlinf.models.embodiment.openpi.dataconfig import get_openpi_config

    effective = build_model_cfg(str(model_path), PI05_EMBODIMENTS['libero'])
    train = get_openpi_config(effective.openpi.config_name, model_path=str(model_path))
    config = train.model
    # The deployed embodiment does not override any preprocessing field. Refuse
    # a future changed config rather than auditing an outdated chain.
    for key in ('max_token_len', 'discrete_state_input', 'pi05', 'action_dim'):
        if key in effective.openpi and effective.openpi[key] != getattr(config, key):
            raise ValueError('Deployed preprocessing override requires explicit audit support: ' + key)
    with cached_downloads_only() as resolved:
        data = train.data.create(train.assets_dirs, config)
        norm = checkpoints.load_norm_stats(str(model_path), data.asset_id)
    processor = transforms.compose([
        transforms.InjectDefaultPrompt(None), *data.data_transforms.inputs,
        transforms.Normalize(norm, use_quantiles=data.use_quantile_norm),
        *data.model_transforms.inputs,
    ])
    fields = ('action_dim', 'action_horizon', 'max_token_len', 'pi05', 'discrete_state_input')
    return processor, dict(config_name=str(effective.openpi.config_name),
                           model_config={key: getattr(config, key) for key in fields},
                           use_quantile_norm=bool(data.use_quantile_norm), asset_id=data.asset_id,
                           transform_order=[type(t).__module__ + '.' + type(t).__name__ for t in processor.transforms],
                           cached_local_paths=resolved,
                           deployed_config_builder_source=source_identity(build_model_cfg),
                           deployed_data_config_source=source_identity(type(train.data)))


def audit_saved_input(model_path, input_npz, inference_log, request_index, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    input_npz, inference_log = Path(input_npz).resolve(), Path(inference_log).resolve()
    before = {str(p): sha256_file(p) for p in (input_npz, inference_log)}
    matching = [json.loads(line) for line in inference_log.read_text().splitlines()
                if json.loads(line).get('request_index') == request_index]
    if len(matching) != 1:
        raise ValueError('Expected exactly one inference record for the request index')
    record = matching[0]
    texts = record['task_descriptions']
    with np.load(input_npz, allow_pickle=False) as source:
        wire = {key: source[key].copy() for key in source.files}
    if len(texts) != 1 or wire['states'].shape[0] != 1:
        raise ValueError('This preflight expects the deployed single-environment batch')
    for key, value in wire.items():
        if array_spec(value) != record['inputs'][key]:
            raise ValueError('Saved input differs from inference receipt: ' + key)
    processor, metadata = deployed_processor(Path(model_path).resolve())
    sample = {'observation/image': wire['main_images'][0],
              'observation/wrist_image': wire['wrist_images'][0],
              'observation/state': wire['states'][0], 'prompt': texts[0]}
    result = processor(sample)
    report = token_audit(find_token_transform(processor), texts[0], result['state'][:wire['states'].shape[-1]],
                         result['tokenized_prompt'], result['tokenized_prompt_mask'])
    arrays = dict(tokenized_prompt=result['tokenized_prompt'],
                  tokenized_prompt_mask=result['tokenized_prompt_mask'], state=result['state'])
    arrays.update({'image_' + key: np.asarray(value) for key, value in result['image'].items()})
    np.savez_compressed(output / 'effective_processor_input.npz', **arrays)
    try:
        from openpi.models.model import Observation
        import torch
        batch = {key: torch.from_numpy(np.asarray(value).copy())[None]
                 for key, value in result.items() if key not in ('image', 'image_mask')}
        batch['image'] = {key: torch.from_numpy(np.asarray(value).copy())[None] for key, value in result['image'].items()}
        batch['image_mask'] = {key: torch.tensor([bool(value)]) for key, value in result['image_mask'].items()}
        observation = Observation.from_dict(batch)
        model_images = {key: array_spec(value.numpy()) for key, value in observation.images.items()}
        observation_source = source_identity(Observation)
    except ImportError:
        model_images, observation_source = None, None
    packages = {}
    for name in ('rpent-openpi', 'rpent-rlinf', 'sentencepiece', 'Pillow', 'torch'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = 'unknown'
    report.update(schema='labsim.pi05.offline_input_audit.v1', request_index=request_index,
                  audit_scope='offline reconstruction using installed deployed processor and saved real wire input; no new model forward',
                  weights_loaded=False, model_service_started=False, network_downloads_allowed=False,
                  task_text_source=dict(path=str(inference_log), source_request_index=request_index, sha256=before[str(inference_log)]),
                  wire_input_source=dict(path=str(input_npz), sha256=before[str(input_npz)]),
                  wire_input={key: array_spec(value) for key, value in wire.items()},
                  installed_processor=metadata, packages=packages,
                  processed_images={key: array_spec(value) for key, value in result['image'].items()},
                  processed_image_mask={key: bool(value) for key, value in result['image_mask'].items()},
                  torch_observation_images=model_images, observation_from_dict_source=observation_source,
                  processor_resize_source=source_identity(type(next(t for t in processor.transforms if type(t).__name__ == 'ResizeImages'))),
                  normalization_source=source_identity(type(next(t for t in processor.transforms if type(t).__name__ == 'Normalize'))),
                  resize_implementation_source=source_identity(__import__('openpi_client.image_tools', fromlist=['resize_with_pad']).resize_with_pad),
                  input_audit_implementation=source_identity(audit_saved_input),
                  normalized_padded_state=result['state'].tolist(),
                  effective_processor_input_sha256=sha256_file(output / 'effective_processor_input.npz'),
                  source_sha256_before=before,
                  source_sha256_after={str(p): sha256_file(p) for p in (input_npz, inference_log)})
    report['source_files_unchanged'] = report['source_sha256_before'] == report['source_sha256_after']
    (output / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-path', required=True)
    parser.add_argument('--input-npz', required=True, help='Closed model service input_NNNNNN.npz')
    parser.add_argument('--inference-log', required=True, help='Closed model service inference.jsonl')
    parser.add_argument('--request-index', required=True, type=int)
    parser.add_argument('--output', required=True, help='New directory; existing output is never overwritten')
    args = parser.parse_args(argv)
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['JAX_PLATFORMS'] = 'cpu'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    report = audit_saved_input(args.model_path, args.input_npz, args.inference_log, args.request_index, args.output)
    print(json.dumps({key: report[key] for key in ('raw_token_count', 'model_max_tokens', 'truncated',
                                                  'active_token_count', 'output_matches_installed_formatting', 'source_files_unchanged')}))


if __name__ == '__main__':
    main()
