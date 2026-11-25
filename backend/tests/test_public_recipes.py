"""RH-08 公共菜谱列表/详情/搜索/筛选的接口测试。"""
from app.models import Recipe, RecipeIngredient, RecipeStep


def _seed_public(session_factory, title="番茄炒蛋", description="家常快手菜", category="家常菜", cuisine="中式"):
    db = session_factory()
    recipe = Recipe(
        owner_id=None,
        title=title,
        description=description,
        category=category,
        cuisine=cuisine,
        cooking_time=10,
        difficulty="简单",
        status="Draft",
        visibility="public",
        orderable=False,
        current_version=1,
    )
    recipe.ingredients = [RecipeIngredient(sort_order=0, ingredient_name="番茄", quantity="2个")]
    recipe.steps = [RecipeStep(step_number=1, instruction="翻炒")]
    db.add(recipe)
    db.commit()
    rid = recipe.id
    db.close()
    return rid


def test_list_public_recipes(client, session_factory):
    _seed_public(session_factory, title="番茄炒蛋")
    _seed_public(session_factory, title="红烧肉")
    resp = client.get("/api/public-recipes")
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()]
    assert set(titles) == {"番茄炒蛋", "红烧肉"}


def test_list_excludes_personal_recipes(client):
    # 用个人接口建一条个人菜谱，公共列表不应包含它
    client.post(
        "/api/recipes",
        json={"title": "我的私房菜", "ingredients": [], "steps": []},
        headers={"X-User-Id": "alice"},
    )
    resp = client.get("/api/public-recipes")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_public_recipe_detail(client, session_factory):
    rid = _seed_public(session_factory, title="红烧肉")
    resp = client.get(f"/api/public-recipes/{rid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "红烧肉"
    assert data["owner_id"] is None
    assert len(data["ingredients"]) == 1
    assert len(data["steps"]) == 1


def test_get_public_recipe_not_found(client):
    assert client.get("/api/public-recipes/99999").status_code == 404


def test_get_personal_recipe_via_public_returns_404(client):
    created = client.post(
        "/api/recipes",
        json={"title": "我的菜", "ingredients": [], "steps": []},
        headers={"X-User-Id": "alice"},
    ).json()
    assert client.get(f"/api/public-recipes/{created['id']}").status_code == 404


def test_search_by_keyword(client, session_factory):
    _seed_public(session_factory, title="番茄炒蛋", description="酸甜开胃")
    _seed_public(session_factory, title="红烧肉", description="咸香软糯")
    resp = client.get("/api/public-recipes", params={"q": "番茄"})
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()]
    assert titles == ["番茄炒蛋"]


def test_search_matches_description(client, session_factory):
    _seed_public(session_factory, title="清炒时蔬", description="低油健康")
    resp = client.get("/api/public-recipes", params={"q": "低油"})
    assert [r["title"] for r in resp.json()] == ["清炒时蔬"]


def test_filter_by_category(client, session_factory):
    _seed_public(session_factory, title="番茄炒蛋", category="家常菜")
    _seed_public(session_factory, title="清蒸鱼", category="海鲜")
    resp = client.get("/api/public-recipes", params={"category": "海鲜"})
    assert [r["title"] for r in resp.json()] == ["清蒸鱼"]


def test_filter_by_cuisine(client, session_factory):
    _seed_public(session_factory, title="番茄炒蛋", cuisine="中式")
    _seed_public(session_factory, title="意面", cuisine="西式")
    resp = client.get("/api/public-recipes", params={"cuisine": "西式"})
    assert [r["title"] for r in resp.json()] == ["意面"]


def test_pagination(client, session_factory):
    for i in range(5):
        _seed_public(session_factory, title=f"菜{i}")
    resp = client.get("/api/public-recipes", params={"skip": 2, "limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2
