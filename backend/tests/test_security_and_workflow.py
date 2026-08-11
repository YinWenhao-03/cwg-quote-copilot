from fastapi.testclient import TestClient

from app.main import app


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_role_permissions_and_quote_approval_workflow() -> None:
    with TestClient(app) as client:
        sales = login(client, "sales@cwg.local", "SalesDemo!2026")
        procurement = login(client, "procurement@cwg.local", "ProcDemo!2026")
        manager = login(client, "manager@cwg.local", "ManagerDemo!2026")
        assert client.get("/supplier-costs", headers=sales).status_code == 403
        assert client.get("/audit-events", headers=procurement).status_code == 403

        inquiry = client.post(
            "/inquiries",
            headers=sales,
            json={
                "raw_text": (
                    "我们是华东汽车科技。请对S4-1000报价300件，纸箱包装，"
                    "发往上海，贸易条款DDP，币种CNY。"
                )
            },
        ).json()
        result = client.post(f"/inquiries/{inquiry['id']}/process", headers=sales).json()
        assert result["status"] == "draft"
        quote_id = result["quote_id"]

        sales_quote = client.get(f"/quotes/{quote_id}", headers=sales).json()
        procurement_quote = client.get(f"/quotes/{quote_id}", headers=procurement).json()
        manager_quote = client.get(f"/quotes/{quote_id}", headers=manager).json()
        assert sales_quote["internal_json"] is None
        assert "hard_floor" not in procurement_quote["internal_json"]
        assert manager_quote["internal_json"]["hard_floor"]

        hard_floor = float(manager_quote["internal_json"]["hard_floor"])
        blocked = client.post(
            f"/quotes/{quote_id}/submit",
            headers=sales,
            json={"proposed_unit_price": hard_floor - 0.01},
        )
        assert blocked.status_code == 422
        assert client.get(f"/quotes/{quote_id}/pdf", headers=sales).status_code == 409

        submitted = client.post(
            f"/quotes/{quote_id}/submit",
            headers=sales,
            json={"proposed_unit_price": sales_quote["proposed_unit_price"]},
        )
        assert submitted.status_code == 200
        approved = client.post(
            f"/quotes/{quote_id}/approve",
            headers=manager,
            json={"decision": "approved", "reason": "标准报价"},
        )
        assert approved.status_code == 200
        pdf = client.get(f"/quotes/{quote_id}/pdf", headers=sales)
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")


def test_missing_field_pauses_and_resumes() -> None:
    with TestClient(app) as client:
        sales = login(client, "sales@cwg.local", "SalesDemo!2026")
        inquiry = client.post(
            "/inquiries",
            headers=sales,
            json={
                "raw_text": (
                    "我们是远航智能汽车。请对S4-1001报价320件，纸箱包装，发往宁波，贸易条款DAP。"
                )
            },
        ).json()
        paused = client.post(f"/inquiries/{inquiry['id']}/process", headers=sales).json()
        assert paused["status"] == "needs_clarification"
        assert paused["extracted"]["missing_fields"] == ["currency"]
        patched = client.patch(
            f"/inquiries/{inquiry['id']}", headers=sales, json={"currency": "CNY"}
        ).json()
        assert patched["missing_fields"] == []
        resumed = client.post(f"/inquiries/{inquiry['id']}/process", headers=sales).json()
        assert resumed["status"] == "draft"


def test_management_document_never_reaches_sales_search() -> None:
    with TestClient(app) as client:
        sales = login(client, "sales@cwg.local", "SalesDemo!2026")
        manager = login(client, "manager@cwg.local", "ManagerDemo!2026")
        payload = {"query": "管理层内部价格政策 硬底价", "top_k": 10}
        sales_results = client.post("/search", headers=sales, json=payload).json()
        manager_results = client.post("/search", headers=manager, json=payload).json()
        assert all(item["metadata"]["classification"] != "management" for item in sales_results)
        assert any(item["metadata"]["classification"] == "management" for item in manager_results)
