"""RH-09 用户饮食画像读取/更新的接口测试。"""


def test_get_profile_returns_empty_default(client):
    resp = client.get("/api/users/profile", headers={"X-User-Id": "alice"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user_id"] is not None
    assert data["dietary_goal"] is None
    assert data["taste_preferences"] is None
    assert data["allergens"] is None
    assert data["max_cooking_time"] is None


def test_update_profile_creates_and_returns(client):
    resp = client.put(
        "/api/users/profile",
        json={
            "dietary_goal": "减脂",
            "taste_preferences": ["清淡", "微辣"],
            "allergens": ["花生"],
            "max_cooking_time": 20,
        },
        headers={"X-User-Id": "alice"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["dietary_goal"] == "减脂"
    assert data["taste_preferences"] == ["清淡", "微辣"]
    assert data["allergens"] == ["花生"]
    assert data["max_cooking_time"] == 20


def test_update_profile_is_partial(client):
    client.put(
        "/api/users/profile",
        json={"dietary_goal": "减脂", "allergens": ["花生"]},
        headers={"X-User-Id": "alice"},
    )
    # 第二次只改一个字段，其余保持原值
    resp = client.put(
        "/api/users/profile",
        json={"dietary_goal": "增肌"},
        headers={"X-User-Id": "alice"},
    )
    data = resp.json()
    assert data["dietary_goal"] == "增肌"
    assert data["allergens"] == ["花生"]  # 未传的字段保持不变


def test_profiles_are_isolated_between_users(client):
    client.put(
        "/api/users/profile",
        json={"dietary_goal": "减脂"},
        headers={"X-User-Id": "alice"},
    )
    resp = client.get("/api/users/profile", headers={"X-User-Id": "bob"})
    data = resp.json()
    assert data["dietary_goal"] is None  # bob 看不到 alice 的画像


def test_update_clears_field_with_null(client):
    client.put(
        "/api/users/profile",
        json={"dietary_goal": "减脂", "allergens": ["花生"]},
        headers={"X-User-Id": "alice"},
    )
    resp = client.put(
        "/api/users/profile",
        json={"allergens": None},
        headers={"X-User-Id": "alice"},
    )
    data = resp.json()
    assert data["allergens"] is None  # 显式传 null 可清空
    assert data["dietary_goal"] == "减脂"  # 其他字段不受影响
