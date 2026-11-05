import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import get_db, set_sync_engine
from backend.app.main import app
from backend.scripts.seed_demo import seed_database


class TestRbacAndAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp_dir.name, "test_noir_auth.db")
        cls.engine = create_engine(
            f"sqlite:///{cls.db_path}",
            connect_args={"check_same_thread": False},
        )
        set_sync_engine(cls.engine, "sqlite_test")
        seed_database(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tmp_dir.cleanup()

    def _auth_header(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_01_public_endpoints_accessible_without_token(self) -> None:
        """Public catalog and policies should allow anonymous access without token."""
        res = self.client.get("/api/catalog/search?limit=5")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("items", data)
        self.assertGreater(len(data["items"]), 0)

        # /api/auth/me without token should return 401
        me_res = self.client.get("/api/auth/me")
        self.assertEqual(me_res.status_code, 401)

    def test_02_customer_registration_and_validation(self) -> None:
        """Customer registration enforces password complexity and creates an authenticated session."""
        # 1. Weak password rejected
        weak_payload = {
            "name": "Weak User",
            "email": "weak@noir.test",
            "password": "short",
        }
        res_weak = self.client.post("/api/auth/register", json=weak_payload)
        self.assertEqual(res_weak.status_code, 422)

        # 2. Strong password accepted
        valid_payload = {
            "name": "Maya Lin",
            "email": "maya.lin@atelier.test",
            "password": "MaisonClient@2026",
            "phone": "+919876543210",
            "preferred_department": "WOMEN",
        }
        res = self.client.post("/api/auth/register", json=valid_payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn("user", data)
        self.assertEqual(data["user"]["email"], "maya.lin@atelier.test")
        self.assertEqual(data["user"]["role"], "customer")
        self.assertIn("tokens", data)
        self.assertIn("access_token", data["tokens"])
        self.assertIn("refresh_token", data["tokens"])

        # 3. Duplicate email rejected with 409 Conflict
        res_dup = self.client.post("/api/auth/register", json=valid_payload)
        self.assertEqual(res_dup.status_code, 409)

    def test_03_login_and_whoami(self) -> None:
        """Login verifies Argon2/scrypt credentials and /me returns actor details."""
        # Valid login for seeded customer
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "arjun@noir.test", "password": "NoirClient@2026", "portal": "customer"},
        )
        self.assertEqual(login_res.status_code, 200)
        data = login_res.json()
        self.assertIn("tokens", data)
        access_token = data["tokens"]["access_token"]
        refresh_token = data["tokens"]["refresh_token"]

        # Call /api/auth/me with access token
        me_res = self.client.get("/api/auth/me", headers=self._auth_header(access_token))
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.json()
        self.assertEqual(me_data["user"]["email"], "arjun@noir.test")
        self.assertEqual(me_data["user"]["role"], "customer")
        self.assertIn("orders:read_own", me_data["permissions"])

        # Invalid password returns 401
        bad_login = self.client.post(
            "/api/auth/login",
            json={"email": "arjun@noir.test", "password": "WrongPassword@123"},
        )
        self.assertEqual(bad_login.status_code, 401)

    def test_04_token_rotation_and_theft_detection(self) -> None:
        """Refreshing tokens issues new pair; reusing old refresh token triggers theft detection."""
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "arjun@noir.test", "password": "NoirClient@2026"},
        )
        tokens = login_res.json()["tokens"]
        rt1 = tokens["refresh_token"]

        # 1. Refresh session with rt1
        refresh_res = self.client.post("/api/auth/refresh", json={"refresh_token": rt1})
        self.assertEqual(refresh_res.status_code, 200)
        refreshed_tokens = refresh_res.json()["tokens"]
        rt2 = refreshed_tokens["refresh_token"]
        at2 = refreshed_tokens["access_token"]
        self.assertNotEqual(rt1, rt2)

        # Valid at2 works
        me_res = self.client.get("/api/auth/me", headers=self._auth_header(at2))
        self.assertEqual(me_res.status_code, 200)

        # 2. Token reuse attack: attempting to use rt1 again should be detected as theft
        replay_res = self.client.post("/api/auth/refresh", json={"refresh_token": rt1})
        self.assertEqual(replay_res.status_code, 401)
        self.assertIn("token_reuse_detected", replay_res.text)

    def test_05_rbac_role_enforcement_and_permission_matrix(self) -> None:
        """Staff roles can access admin endpoints while customers receive 403 Forbidden."""
        # Customer token
        cust_login = self.client.post(
            "/api/auth/login",
            json={"email": "arjun@noir.test", "password": "NoirClient@2026"},
        )
        cust_token = cust_login.json()["tokens"]["access_token"]

        # Customer attempting to access admin dashboard -> 403 Forbidden
        admin_res = self.client.get("/api/admin/dashboard", headers=self._auth_header(cust_token))
        self.assertEqual(admin_res.status_code, 403)

        # Staff manager token
        mgr_login = self.client.post(
            "/api/auth/login",
            json={"email": "manager@noir.test", "password": "NoirAdmin@2026", "portal": "admin"},
        )
        self.assertEqual(mgr_login.status_code, 200)
        mgr_token = mgr_login.json()["tokens"]["access_token"]

        # Manager accessing admin dashboard -> 200 OK
        mgr_dash = self.client.get("/api/admin/dashboard", headers=self._auth_header(mgr_token))
        self.assertEqual(mgr_dash.status_code, 200)

        # Manager accessing RBAC matrix -> 200 OK with canonical roles
        matrix_res = self.client.get("/api/admin/rbac/matrix", headers=self._auth_header(mgr_token))
        self.assertEqual(matrix_res.status_code, 200)
        roles = matrix_res.json()["roles"]
        role_codes = {r.get("role_code") or r.get("code") for r in roles}
        self.assertIn("super_admin", role_codes)
        self.assertIn("manager", role_codes)
        self.assertIn("catalog_manager", role_codes)
        self.assertIn("finance_admin", role_codes)
        self.assertIn("support_agent", role_codes)
        self.assertIn("customer", role_codes)

    def test_06_admin_staff_provisioning_flow(self) -> None:
        """Staff registration requires invite code or super admin token."""
        # 1. Registration with invalid invite code fails
        bad_invite = {
            "name": "Intruder",
            "email": "intruder@noir.test",
            "password": "IntruderPass@2026",
            "role_code": "manager",
            "invite_code": "wrong_code",
        }
        res_bad = self.client.post("/api/auth/register/admin", json=bad_invite)
        self.assertEqual(res_bad.status_code, 403)

        # 2. Registration with valid Maison invite code succeeds
        valid_invite = {
            "name": "Sarah Connor",
            "email": "sarah.connor@noir.test",
            "password": "NoirStaff@2026",
            "role_code": "catalog_manager",
            "department_scope": "WOMEN",
            "invite_code": "NOIR-ATELIER-ADMIN-2026",
        }
        res_valid = self.client.post("/api/auth/register/admin", json=valid_invite)
        self.assertEqual(res_valid.status_code, 201)
        data = res_valid.json()
        self.assertEqual(data["user"]["role"], "catalog_manager")
        self.assertTrue(data["user"]["is_staff"])

        # 3. New staff member can login
        staff_login = self.client.post(
            "/api/auth/login",
            json={"email": "sarah.connor@noir.test", "password": "NoirStaff@2026", "portal": "admin"},
        )
        self.assertEqual(staff_login.status_code, 200)
        staff_token = staff_login.json()["tokens"]["access_token"]

        # Staff can access catalog metadata and inventory (catalog_manager permission)
        meta_res = self.client.get("/api/catalog/meta", headers=self._auth_header(staff_token))
        self.assertEqual(meta_res.status_code, 200)
        self.assertIn("categories", meta_res.json())

    def test_07_sessions_and_revocation(self) -> None:
        """User can list active sessions and revoke a specific session or logout all."""
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "curator@noir.test", "password": "NoirAdmin@2026"},
        )
        tokens = login_res.json()["tokens"]
        curator_at = tokens["access_token"]
        curator_rt = tokens["refresh_token"]

        # List active sessions
        sessions_res = self.client.get("/api/auth/sessions", headers=self._auth_header(curator_at))
        self.assertEqual(sessions_res.status_code, 200)
        sessions = sessions_res.json()
        self.assertGreater(len(sessions), 0)

        # Logout current session
        logout_res = self.client.post(
            "/api/auth/logout",
            json={"refresh_token": curator_rt},
            headers=self._auth_header(curator_at),
        )
        self.assertEqual(logout_res.status_code, 200)

        # Refresh with logged out token fails
        fail_refresh = self.client.post("/api/auth/refresh", json={"refresh_token": curator_rt})
        self.assertEqual(fail_refresh.status_code, 401)

    def test_08_backward_compatibility_with_demo_tokens(self) -> None:
        """Existing test harness mock tokens continue to resolve correctly."""
        # Demo customer token
        demo_cus = self.client.get("/api/auth/me", headers=self._auth_header("demo_CUS-001"))
        self.assertEqual(demo_cus.status_code, 200)
        self.assertEqual(demo_cus.json()["user"]["role"], "customer")

        # Demo admin token
        demo_admin = self.client.get("/api/auth/me", headers=self._auth_header("admin_manager"))
        self.assertEqual(demo_admin.status_code, 200)
        self.assertEqual(demo_admin.json()["user"]["role"], "manager")

        # Service account token on allowed service endpoint
        demo_svc = self.client.get("/api/catalog/search?limit=2", headers=self._auth_header("svc-catalog"))
        self.assertEqual(demo_svc.status_code, 200)


if __name__ == "__main__":
    unittest.main()
