import hashlib
from pathlib import Path
from surveillance_addons.integrity import validate_model_file
def test_checksum_validation(tmp_path: Path):
    file=tmp_path/"model.bin"; file.write_bytes(b"model")
    validate_model_file(file,hashlib.sha256(b"model").hexdigest())
