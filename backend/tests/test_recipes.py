"""RH-07 个人菜谱 CRUD + 一键导入的接口测试。"""
from app.models import Recipe, RecipeIngredient, RecipeStep


def _create_payload(**overrides):
    payload = {
        "title": "番茄炒蛋",
        "description": "家常快手菜",
        "category": "家常菜",
        "cuisine": "中式",
        "cooking_time": 10,
        "difficulty": "简单",
        "ingredients": [
            {"ingredient_name": "番茄", "quantity": "2个", "sort_order": 0},
            {"ingredient_name": "鸡蛋", "quantity": "3个", "sort_order": 1},
        ],
        "steps": [
            {"step_number": 1, "instruction": "炒蛋", "heat_level": "中火"},
            {"step_number": 2, "instruction": "下番茄翻炒", "heat_level": "中火"},
        ],
    }
    payload.update(overrides)
    return payload


def _seed_public_recipe(session_factory, **overrides):
    """往临时库直接塞一条公共菜谱（owner_id=None），返回其 id。"""
    db = session_factory()
    recipe = Recipe(
        owner_id=None,
        title=overrides.get("title", "红烧肉"),
        description="经典家常菜",
        category="家常菜",
        cuisine="中式",
        cooking_time=60,
        difficulty="中等",
        status="Draft",
        visibility="public",
        orderable=False,
        current_version=1,
    )
    recipe.ingredients = [RecipeIngredient(sort_order=0, ingredient_name="五花肉", quantity="500克")]
    recipe.steps = [RecipeStep(step_number=1, instruction="焯水后红烧")]
    db.add(recipe)
    db.commit()
    rid = recipe.id
    db.close()
    return rid


# ---------- 创建 / 列表 / 详情 ----------

def test_create_recipe(client):
    resp = client.post("/api/recipes", json=_create_payload(), headers={"X-User-Id": "alice"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "番茄炒蛋"
    assert data["status"] == "Draft"
    assert data["visibility"] == "private"
    assert data["orderable"] is False
    assert data["owner_id"] is not None
    assert len(data["ingredients"]) == 2
    assert len(data["steps"]) == 2
    assert data["ingredients"][0]["ingredient_name"] == "番茄"


def test_list_recipes_only_own(client):
    client.post("/api/recipes", json=_create_payload(title="甲菜"), headers={"X-User-Id": "alice"})
    client.post("/api/recipes", json=_create_payload(title="乙菜"), headers={"X-User-Id": "bob"})
    resp = client.get("/api/recipes", headers={"X-User-Id": "alice"})
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()]
    assert titles == ["甲菜"]  # 只看到自己的，看不到 bob 的


def test_get_recipe_detail(client):
    created = client.post("/api/recipes", json=_create_payload(), headers={"X-User-Id": "alice"}).json()
    resp = client.get(f"/api/recipes/{created['id']}", headers={"X-User-Id": "alice"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == created["id"]
    assert data["steps"][0]["instruction"] == "炒蛋"


def test_get_recipe_not_found(client):
    resp = client.get("/api/recipes/99999", headers={"X-User-Id": "alice"})
    assert resp.status_code == 404


def test_get_other_users_recipe_returns_404(client):
    created = client.post("/api/recipes", json=_create_payload(), headers={"X-User-Id": "alice"}).json()
    resp = client.get(f"/api/recipes/{created['id']}", headers={"X-User-Id": "bob"})
    assert resp.status_code == 404  # 隔离：bob 看不到 alice 的菜谱


# ---------- 更新 ----------

def test_update_recipe_partial(client):
    created = client.post("/api/recipes", json=_create_payload(), headers={"X-User-Id": "alice"}).json()
    resp = client.put(
        f"/api/recipes/{created['id']}",
        json={"title": "少糖版番茄炒蛋"},
        headers={"X-User-Id": "alice"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "少糖版番茄炒蛋"
    assert data["cooking_time"] == 10  # 未传的字段保持原值


def test_update_recipe_replace_ingredients(client):
    created = client.post("/api/recipes", json=_create_payload(), headers={"X-User-Id": "alice"}).json()
    resp = client.put(
        f"/api/recipes/{created['id']}",
        json={"ingredients": [{"ingredient_name": "番茄", "quantity": "1个", "sort_order": 0}]},
        headers={"X-User-Id": "alice"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["ingredients"]) == 1  # 整体替换


def test_update_other_users_recipe_returns_404(client):
    created = client.post("/api/recipes", json=_create_payload(), headers={"X-User-Id": "alice"}).json()
    resp = client.put(f"/api/recipes/{created['id']}", json={"title": "x"}, headers={"X-User-Id": "bob"})
    assert resp.status_code == 404


# ---------- 删除 ----------

def test_delete_recipe(client):
    created = client.post("/api/recipes", json=_create_payload(), headers={"X-User-Id": "alice"}).json()
    resp = client.delete(f"/api/recipes/{created['id']}", headers={"X-User-Id": "alice"})
    assert resp.status_code == 204
    assert client.get(f"/api/recipes/{created['id']}", headers={"X-User-Id": "alice"}).status_code == 404


# ---------- 一键导入 ----------

def test_import_public_recipe(client, session_factory):
    public_id = _seed_public_recipe(session_factory)
    resp = client.post("/api/recipes/import", json={"source_recipe_id": public_id}, headers={"X-User-Id": "alice"})
    assert resp.status_code == 200, resp.text
    new_id = resp.json()["recipe_id"]

    detail = client.get(f"/api/recipes/{new_id}", headers={"X-User-Id": "alice"}).json()
    assert detail["status"] == "Imported"
    assert detail["source_recipe_id"] == public_id
    assert detail["title"] == "红烧肉"
    assert len(detail["ingredients"]) == 1
    assert len(detail["steps"]) == 1


def test_import_duplicate_returns_409(client, session_factory):
    public_id = _seed_public_recipe(session_factory)
    first = client.post("/api/recipes/import", json={"source_recipe_id": public_id}, headers={"X-User-Id": "alice"})
    assert first.status_code == 200
    second = client.post("/api/recipes/import", json={"source_recipe_id": public_id}, headers={"X-User-Id": "alice"})
    assert second.status_code == 409


def test_import_nonexistent_returns_404(client):
    resp = client.post("/api/recipes/import", json={"source_recipe_id": 99999}, headers={"X-User-Id": "alice"})
    assert resp.status_code == 404


def test_import_personal_recipe_returns_404(client):
    created = client.post("/api/recipes", json=_create_payload(), headers={"X-User-Id": "alice"}).json()
    resp = client.post("/api/recipes/import", json={"source_recipe_id": created["id"]}, headers={"X-User-Id": "bob"})
    assert resp.status_code == 404  # 个人菜谱不能作为导入来源
