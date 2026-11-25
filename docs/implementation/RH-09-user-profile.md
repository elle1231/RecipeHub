# RH-09 用户饮食画像（读取 / 更新）

## 1. 一句话总结

把 `user_profiles` 表接上「读 + 更新」两个接口：画像与用户一对一、首次读写自动建行（lazy），更新走部分更新语义，为后面 Day 4 的个性化推荐提供「用户长期偏好」这个结构化数据源。

## 2. 在项目中的位置

画像字段（饮食目标、口味、忌口、过敏原、习惯、最长烹饪时间）是「个性化推荐」和「菜单规划」的硬约束来源——过敏原过滤、口味匹配、耗时筛选都读它。RH-09 只负责把这份数据可靠地读写出来，推荐逻辑本身在 Day 4。

- `backend/app/api/users.py` —— 路由：`GET/PUT /api/users/profile`。
- `backend/app/services/user/service.py` —— 业务：`get_or_create_user` + `get_or_create_profile` + 读/更新。
- `backend/tests/test_profile.py` —— 5 条接口测试（含空画像、部分更新、用户隔离、null 清空）。

## 3. 实现细节

### 3.1 接口

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/api/users/profile` | 读取画像；无画像时返回一条空画像（字段全 null） |
| PUT | `/api/users/profile` | 部分更新；无画像时先建行再更新 |

### 3.2 数据流

```
请求头 X-User-Id (openid)
        ↓  get_or_create_user → users.id
        ↓  get_or_create_profile → user_profiles（不存在则建空行）
        ↓  PUT: model_dump(exclude_unset=True) 只改传入字段
返回 UserProfileRead（from_attributes）
```

## 4. 设计决策与权衡（面试重点）

- **为什么「读画像」也会有副作用（首次读就建一行空画像）？**
  - 权衡点：读接口本应无副作用。但 `UserProfileRead` 需要 `id`/`updated_at` 这两个数据库生成字段，没有行就拼不出合法响应。与其让 GET 在「无画像」时返回一个不完整对象或 404（前端还要判断「没设过」），不如 lazy 建一条空画像，让「从未设置」和「设置了空值」统一成同一种状态——前端拿到空画像渲染空表单即可。`user_id` 唯一约束保证每个用户至多一条，不会越建越多。

- **为什么更新用 `exclude_unset=True` 而不是 `exclude_none=True`？**
  - 画像字段天然可空，且「清空」是合法操作（比如用户想去掉过敏原标记，发 `{"allergens": null}`）。`exclude_unset` 区分「没传（不改）」和「显式传 null（清空）」；`exclude_none` 会把这两种混为一谈，导致「想清空却清不掉」。这和 RH-07 菜谱部分更新是同一套语义，保持全项目一致。

- **为什么 `taste_preferences`/`allergens` 这些用 JSON 数组而不是拆表？**
  - 这些是「一个用户、一整组偏好」的整读整写数据，查询粒度是「整个画像」，从不需要单独查「哪个用户对花生过敏」再聚合。拆表是过度设计（RH-05 已定「按访问粒度决定拆表还是 JSON」这个原则，这里再次落地）。

- **为什么画像和用户分两张表（`users` vs `user_profiles`）而不是塞进 `users` 里加列？**
  - 画像字段多、可空、且属于「长期偏好」这个独立域；身份信息（openid/nickname）和偏好信息（目标/口味/过敏原）变更频率、访问场景都不同。拆开还能保证「更新画像」不碰用户身份表，将来加字段（比如更多偏好维度）也不动 `users`。

## 5. 面试高频问题 & 回答要点

**Q1：饮食画像是怎么存的？为什么用 JSON？**
要点：`users` 一对一 `user_profiles`；目标/口味/忌口/过敏原等偏好是「整读整写」数据，用 JSON 数组列存；身份（openid）和偏好分表，域边界清晰。

**Q2：怎么保证画像更新是「部分更新」？**
要点：`UserProfileUpdate` 全字段可选，`model_dump(exclude_unset=True)` 只取显式传入字段，未传的保持原值；显式传 null 可清空，和「没传」区分开。

**Q3：为什么读画像接口会建数据（副作用）？**
要点：`UserProfileRead` 需要数据库生成的 `id`/`updated_at`，没有行就拼不出合法响应；用 lazy 建空画像统一「未设置」和「空值」两种状态，`user_id` 唯一约束兜底不会重复建。

## 6. 踩坑

- **`exclude_unset` 对 `null` 的处理**：`{"allergens": null}` 里 `allergens` 是「显式传入 null」，`exclude_unset` 会保留它 → 正确清空。别在这里用 `exclude_none`，否则清空失效（测试 `test_update_clears_field_with_null` 专门兜这个）。

- **JSON 列和 SQLite**：SQLAlchemy 的 `JSON` 列在 SQLite 里存文本、读回自动反序列化成 list/dict，所以 `taste_preferences` 返回时是真正的数组而不是字符串。别手动 `json.loads`，否则会二次反序列化报错。

- **`onupdate=utcnow` 只在真正 UPDATE 时触发**：`PUT {}`（空 body）时 `exclude_unset` 得到空 dict，没有字段变更就不会发 UPDATE，`updated_at` 不会变——这是对的，别误以为「每次 PUT 都该刷新时间」。

- **空画像与 404 的取舍**：这里选择「无画像返回空画像」而不是 404，因为对前端来说「没设过画像」不是错误，是正常的初始状态。如果改成 404，前端每次都要处理「首次进入」的特殊分支，徒增复杂度。
