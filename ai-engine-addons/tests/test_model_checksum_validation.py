import hashlib
from pathlib import Path
from surveillance_addons.integrity import validate_model_file
def test_model_files_are_checksum_validated(tmp_path: Path):
    path=tmp_path/"model.pt"; path.write_bytes(b"weights")
    validate_model_file(path,hashlib.sha256(b"weights").hexdigest())
