import unittest
from reatoon.view_scope import member_mask

class ViewScopeTests(unittest.TestCase):
    def test_group_includes_descendants_not_similar_names(self):
        names=['|root|group|a|shape','|root|group|nested|b|shape','|root|groupOther|a|shape']
        self.assertEqual(member_mask(names,['|root|group']).tolist(),[True,True,False])
    def test_instances_are_path_specific(self):
        names=['|instanceA|shape','|instanceB|shape']
        self.assertEqual(member_mask(names,['|instanceA']).tolist(),[True,False])
    def test_selected_shape_and_component_owner(self):
        names=['|a|shape','|b|shape']
        self.assertEqual(member_mask(names,['|b|shape.f[2:4]']).tolist(),[False,True])
    def test_empty_scope_hides_everything(self):
        self.assertEqual(member_mask(['|a|shape','|b|shape'],[]).tolist(),[False,False])
        self.assertEqual(member_mask([],['|a']).tolist(),[])

if __name__=='__main__':unittest.main()
