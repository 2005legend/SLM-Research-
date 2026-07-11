from pathlib import Path
import shutil
import tempfile

from local_sage.validation.contracts import ContractChecker

repo_root = Path('.').resolve()
temp_dir = Path(tempfile.mkdtemp(prefix='local_sage_contract_violation_'))
shutil.copytree(repo_root, temp_dir, dirs_exist_ok=True)

bad_code = '''async def generate(self, prompt: str, system: str = '') -> ModelResponse:
    if not prompt:
        raise RuntimeError('wrong exception type — should be OllamaError')
    pass
'''

test_file = temp_dir / 'test_contract_violation.py'
test_file.write_text(bad_code, encoding='utf-8')

checker = ContractChecker()
contracts = checker.load_contracts(Path('.'))
print('checker loaded', len(contracts), 'contracts')
failures = checker.check(temp_dir)
print('failures found:', len(failures))
for f in failures:
    print(' -', f.symbol_id, '|', f.constraint, '|', f.actual[:80])
print('temp dir:', temp_dir)
