from runpy import run_path
p = r"c:\Users\HomePC\Documents\Coding projects\Expense tracker.py"
ns = run_path(p)
Expense = ns['Expense']
ExpenseManager = ns['ExpenseManager']

# create an expense and manager
e = Expense(amount='10.00', description='Test Item', category='food', date='2025-01-01')
mgr = ExpenseManager()
mgr.add(e)
print('count=', len(mgr.expenses))
print('find index1=', mgr.find_by_index(1))
print('formatted=', mgr.find_by_index(1).formatted())
