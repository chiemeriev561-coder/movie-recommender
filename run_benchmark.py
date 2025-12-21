from importlib import util
import sys
spec = util.spec_from_file_location('expense_tracker_module', r'C:\Users\HomePC\Documents\Coding projects\Expense tracker.py')
m = util.module_from_spec(spec)
# Ensure module is present in sys.modules before executing (helps dataclass decorator lookups)
sys.modules['expense_tracker_module'] = m
spec.loader.exec_module(m)
# run with 20000 items
m.run_profiled_benchmark(20000)
print('Benchmark finished.')
