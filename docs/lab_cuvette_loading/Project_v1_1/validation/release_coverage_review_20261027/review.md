# Project_v1_1 独立发布覆盖检查

Stage7 is accurate as an explicitly incomplete cutoff draft; final release remains pending actual GPT06/same-source regression, final source/CI and authored/rendered deliverables.

本审查只读取源码、文档和已关闭的精简证明；没有读取任何活动 episode、H5 或物理原始流，没有调用模型或启动 GPU。只新增本目录两份审查文件。

当前 HEAD：`9a4713cf8c71bed4d697625ab052b378608780cc`。stage7 的 90 个本地实体 SHA256 与大小全部匹配，另有一个固定 HF URL。

## 已核对范围

- **draft_cutoff**：pass_at_stated_cutoff。Stage7 finalized=false. Teacher5/5 at0b922ec, extra58da teacher success separately; GPT01–05 distinct debug failures, formal0/5. GPT06 explicitly pending; no future result claimed.
- **source_registry**：pass。90/90 local source SHA256 and declared bytes match; one pinned HF URL is not a local entity. This audit does not refetch HF or inspect H5.
- **environment_invocation**：CPU_dry_run_pass_only。Actual ./labsim eval --project-version Project_v1_1 --scene standard --backend teacher --episodes1 --headless --dry-run routes to new module/config. files_created=false/simulation_started=false; output directory absent. No new native environment run by reviewer.
- **portable_setup**：documentation_and_existing_proof。Explicit existing IsaacPython, isolated Shapely, pinned independent revision cache83files/82HF+externalFranka; cache and install alternatives distinguished, no original workstation absolute path needed in documented commands. Existing closed H5 proof shows40datasets/noExternalLink/externalstorage/VDS and alternate-path ACT/DP; not second-machine deployment.
- **public_GPT_scope**：pass_static_and_existing_closed_proof。Whitelist RGB side/wrist,robot joints/TCP,static task goals/calibration,IDs and declared finger-contact scalars. Generic move/gripper/wait/observe/finish only; public facade rejects private phase metadata. P7 fixed JPEG crop only; no GT bbox, current object/seat pose, expert action/route or hidden automatic task stage. Teacher truth use explicitly separate.
- **generic_hold**：pass_static_and_existing_closed_proof。GenericContactHold inputs: public measuredfinger positions/contact plus requested/ramped/applied opening, time, effort, configured mass/friction assumptions. No object pose or teacher phase; explicit release wins. It does not change physical gains/friction/score. Static sensor is object-filtered cup_fingers pair, not all-fingertip total contact.
- **taxonomy_reader**：pass_static_and_existing_closed_proof。Stage7 safety collisions remain record/integrity/physics true with BCfalse; task slip separate. Reader rejects execution/service/simulation and control_diagnostic; accepts qualifying loading natural/deviation task/safety/budget failures, success additionally needs BC eligibility. Null post_retreat stable preserved when no actual retreat. physics_trustworthy means current checks, not full cooked geometry/force calibration.
- **numerical_claims**：no_new_unsupported_number_identified_in_selected_checks。Teacher5 and7539 transitions;40dataset/1,944,284,458B portable proof; GPT05 normal failure ACT/DP and success rejection;717CPU/13skip all supported by named compact evidence. This is not an independent recomputation from raw physical streams or H5.

## 最强剩余缺口

- **gpt_complete_task_success**：pending_GPT06_actual_end_result。Only actual standard-reset GPT grasp/extract/transport/originalA loading/support/open/detach/retreat/stable3s can satisfy. Do not replace with teacher or replay.
- **gpt_formal5**：not_run_gate_unmet_at_stage7。Start only after actual full GPT debug success, freeze all policy/vision/tools/control/scorer; budget may limit actual completedcount.
- **final_runtime_release**：pending_current_native_and_closed_data_audits。Record exact9a4713c/current final runtime, clean checkout/independentcache proof, same-source teacher and GPT exit0/closedH5/normalreader/videoactualinput QA; final remoteSHA+CI receipt. OlderCI37 cannot certify final source.
- **visual_observability**：partially_verified。Teacher stage previews are not model inputs. P7 offline D24 is not actualmodelinput. Final GPT06 actual JPEG/manifest+requestbinding required. Prior actualQA did notrecognize earlysmallslip; no claim allstagesunoccluded. WristVERIFYclip/sideocclusion remain.
- **reset_repeatability**：scope_limit。Five teacher runs are five independentprocesses, not a fiveepisode sameprocess reset test. Existing free-space3reset diagnostic does not prove full-loading repeatedreset. Keep commandcapability distinct from actualtested scope.
- **report_and_reading_pack**：not_authored_or_packaged_at_stage7。Final actual inputs/SHAs, DOCX allpages render QA, allrelative video/image/config dependencies, fullreading videos provenance and ≤80MB validation; keepnative/oldoutputs unchanged.

## 最终收口建议

- README.md：P6 尚待真实策略验证 is stale after actual GPT05 P6 transport run. Prefer 已有真实搬运调试，100µm近座插入策略尚未验证. No performance improvement inference.
- docs/lab_cuvette_loading/Project_v1_1/README.md：Clarify public finger_contact_N is norm of normal-force vector on cuvette filtered separately by left/rightfinger (cup_fingers), not total all-object fingertip contact, friction vector, forcecap or target support. This identity-conditioned sensor is already implemented, not a new GT pose feed.
- final_report：completed only interval ended; target_reached is actualTCP1mm/.5deg only, not task/gripper. Maximum receipt trackingerror is sampled at completedcontrolboundaries; physics-substep extrema are separate. Use no broad micrometreaccuracy or guaranteedcollisionfree language.

未发现选定证据范围内新增的无依据数字；不代表从原始物理流重新计算了全部统计。精细位移是空爪合法无接触诊断，不能外推持物接触精度；原生速度/差分分歧与有效 cooked 表面未知继续保留。

机器可读证据、检查时 SHA 和全部来源在 [review.json](review.json)。
