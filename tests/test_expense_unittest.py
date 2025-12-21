import unittest
import tempfile
import json
from pathlib import Path
from runpy import run_path

MODULE_PATH = Path(__file__).resolve().parents[1] / 'Expense tracker.py'


def load_ns():
    return run_path(str(MODULE_PATH))


class ExpenseTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_ns()
        self.Expense = self.ns['Expense']
        self.normalize_category = self.ns['normalize_category']

    def test_normalize_category(self):
        Category = self.ns['Category']
        self.assertEqual(self.normalize_category('food'), Category.FOOD)
        self.assertEqual(self.normalize_category(' FOOD '), Category.FOOD)
        self.assertEqual(self.normalize_category('Transport'), Category.TRANSPORT)
        self.assertEqual(self.normalize_category('other'), Category.OTHER)

    def test_negative_amount_raises(self):
        with self.assertRaises(ValueError):
            self.Expense(amount='-1', description='bad', category='Other')

    def test_serialization_roundtrip(self):
        e = self.Expense(amount='12.50', description='Lunch', category='food', date='2025-12-01', notes='sandwich')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'tmp_expenses.json'
            save_to_json = self.ns['save_to_json']
            load_from_json = self.ns['load_from_json']
            save_to_json(str(p), [e])
            loaded = load_from_json(str(p))
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0], e)


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_ns()
        self.Expense = self.ns['Expense']
        self.ExpenseManager = self.ns['ExpenseManager']

    def test_add_find_remove(self):
        mgr = self.ExpenseManager()
        e = self.Expense(amount='5', description='Bus', category='transport', date='2025-01-02')
        mgr.add(e)
        self.assertEqual(len(mgr.expenses), 1)
        self.assertIs(mgr.find_by_index(1), e)
        mgr.remove(e)
        self.assertEqual(len(mgr.expenses), 0)

    def test_sorting_deterministic(self):
        a = self.Expense(amount='10.00', description='apple', category='food', date='2025-01-01')
        b = self.Expense(amount='10.00', description='Banana', category='food', date='2025-01-01')
        c = self.Expense(amount='5.00', description='carrot', category='food', date='2025-01-02')
        mgr = self.ExpenseManager([c, b, a])
        ordered = mgr.list_sorted()
        # same date+amount: description order should be case-insensitive
        self.assertEqual(ordered[0].description.lower(), 'apple')
        self.assertEqual(ordered[1].description.lower(), 'banana')
        self.assertEqual(ordered[2], c)

    def test_update_via_manager(self):
        mgr = self.ExpenseManager()
        e = self.Expense(amount='7', description='Coffee', category='food', date='2025-01-05')
        mgr.add(e)
        self.assertTrue(mgr.update(0, description='Latte'))
        self.assertEqual(mgr.find_by_index(1).description, 'Latte')

    def test_ndjson_save_and_background_save(self):
        save_to_json = self.ns['save_to_json']
        load_from_json = self.ns['load_from_json']
        save_to_json_async = self.ns['save_to_json_async']
        wait_for_background_saves = self.ns['wait_for_background_saves']
        # Generate sample expenses
        exs = [self.Expense(amount=str(i+1), description=f'Item {i}', category='Other', date='2025-01-01') for i in range(50)]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'test_ndjson.json'
            # Test NDJSON save/load
            save_to_json(str(p), exs, ndjson=True)
            loaded = load_from_json(str(p))
            self.assertEqual(len(loaded), len(exs))
            # Test background save
            p2 = Path(d) / 'test_bg.json'
            t = save_to_json_async(str(p2), exs, ndjson=True)
            # Wait for background saves to complete
            wait_for_background_saves()
            self.assertTrue(p2.exists())
            loaded2 = load_from_json(str(p2))
            self.assertEqual(len(loaded2), len(exs))


if __name__ == '__main__':
    unittest.main()
