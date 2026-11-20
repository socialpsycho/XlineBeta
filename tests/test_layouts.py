import unittest
from xlinebot.games.layouts import generate_mines,generate_tower_layout
class LayoutTests(unittest.TestCase):
    def test_mines_layout_has_expected_unique_cells(self):
        result=generate_mines(); self.assertEqual(len(result),3); self.assertEqual(len(set(result)),3); self.assertTrue(all(0<=x<9 for x in result))
    def test_tower_generates_every_floor(self):
        result=generate_tower_layout(4,1,9); self.assertEqual(set(result),set(range(9))); self.assertTrue(all(len(v)==1 and 0<=v[0]<4 for v in result.values()))
if __name__=="__main__": unittest.main()
