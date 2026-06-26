from pathlib import Path
from local_sage.validation.runner import ValidationRunner
p = Path('c:/Users/USER/sidaarth/SLM research')
patch = Path('test.diff').read_text()
vr = ValidationRunner(p)
res = vr._pre_validate(patch)
out = Path('prevalidate_out.txt')
with out.open('w', encoding='utf8') as f:
    f.write(repr(res) + "\n")
    if res is not None:
        for fline in res.failures:
            f.write(f"{fline.tool}: {fline.message}\n")
    else:
        f.write('pre-validate passed (None)\n')
