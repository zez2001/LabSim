"""Thin version-specific CLI over the already validated environment runner."""
from pathlib import Path
from demos.lab_cuvette_env_v1.run import parser,main

if __name__=='__main__':
    p=parser();p.set_defaults(config=Path('config/lab_cuvette_loading/Size_v1/standard.yaml'))
    p.add_argument('--asset-id',help='Registered XY-only vessel hypothesis; original seat and physical parameters unchanged')
    raise SystemExit(main(p.parse_args()))
