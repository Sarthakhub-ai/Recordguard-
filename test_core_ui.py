import os
import tempfile
import unittest

import database
from functions import create_initial_owner, authenticate_user, register_patient, create_new_user

class CoreBackendSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=database.DB_PATH
        database.DB_PATH=os.path.join(self.tmp.name,'recordguard.db')
        database.initialize_database()
    def tearDown(self):
        database.DB_PATH=self.old
        self.tmp.cleanup()
    def test_owner_patient_and_users(self):
        owner=create_initial_owner('owner1','StrongPass123','Owner One')
        self.assertEqual(owner['role'],'owner')
        patient=register_patient(owner,'Test Patient','30','M','1996-01-01','A','A','9876543210','O+')
        self.assertTrue(patient['patient_id'])
        create_new_user(owner,'doc1','StrongPass123','doctor','Doctor One')
        create_new_user(owner,'staff1','StrongPass123','staff','Staff One')
        create_new_user(owner,'pat1','StrongPass123','patient','Patient One',patient['patient_id'])
        self.assertEqual(authenticate_user('doc1','StrongPass123')['role'],'doctor')
        self.assertEqual(authenticate_user('pat1','StrongPass123')['patient_id'],patient['patient_id'])

if __name__=='__main__': unittest.main()
