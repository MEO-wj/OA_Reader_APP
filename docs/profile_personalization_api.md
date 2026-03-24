# 个人中心个性化资料预留接口文档

## 文档说明

本文档描述个人中心个性化资料模块所预留的后端接口，供前后端协作时直接查阅。

当前状态：

- 前端实现为本地优先保存
- 后端已注册占位路由
- 占位路由当前统一返回 `501 Not Implemented`
- 前端默认不会主动调用这些接口，除非显式开启 `EXPO_PUBLIC_PROFILE_REMOTE_SYNC=1`

基础 URL：

- 生产环境：`https://oap-backend.handywote.top/api`
- 本地开发：`http://localhost:4420/api`

认证方式：

- 所有接口都要求 `Authorization: Bearer <access_token>`

---

## 1. 获取个人资料

### 请求

```http
GET /user/profile
Authorization: Bearer <access_token>
```

### 设计用途

- 在未来的服务端同步版本中获取用户最新个人资料
- 当前前端本地资料结构与该接口返回结构保持一致

### 目标响应结构

```json
{
  "id": "user_uuid",
  "username": "20240001",
  "display_name": "陈子俊",
  "avatar_url": "https://cdn.example.com/avatar/20240001.jpg",
  "profile_tags": ["计算机", "阅读", "夜猫子"],
  "bio": "喜欢把通知系统做得更顺手一点。",
  "profile_updated_at": "2026-03-23T09:30:00.000Z",
  "is_vip": false,
  "vip_expired_at": null
}
```

### 当前占位行为

当前 backend 占位路由会返回：

```json
{
  "error": "个人资料接口已预留，暂未接入服务端持久化实现",
  "code": "profile_api_reserved",
  "reserved": true,
  "method": "GET",
  "path": "/api/user/profile",
  "data": {
    "id": "user_uuid",
    "display_name": "当前登录用户名称",
    "avatar_url": null,
    "profile_tags": [],
    "bio": null,
    "profile_updated_at": null
  }
}
```

状态码：`501`

---

## 2. 更新个人资料

### 请求

```http
PATCH /user/profile
Authorization: Bearer <access_token>
Content-Type: application/json
```

### 请求体

```json
{
  "display_name": "陈子俊",
  "profile_tags": ["计算机", "效率控", "摄影"],
  "bio": "喜欢把通知系统做得更顺手一点。",
  "avatar_url": "https://cdn.example.com/avatar/20240001.jpg",
  "profile_updated_at": "2026-03-23T09:30:00.000Z"
}
```

### 字段约定

- `display_name`
  说明：昵称
  类型：`string`
  建议范围：2-20 字

- `profile_tags`
  说明：个性化标签列表
  类型：`string[]`
  建议范围：最多 5 个，每个 2-10 字

- `bio`
  说明：个人简介
  类型：`string`
  建议范围：0-80 字

- `avatar_url`
  说明：头像上传成功后的远端地址
  类型：`string`

- `profile_updated_at`
  说明：资料更新时间
  类型：ISO 8601 时间字符串

### 目标响应结构

```json
{
  "id": "user_uuid",
  "username": "20240001",
  "display_name": "陈子俊",
  "avatar_url": "https://cdn.example.com/avatar/20240001.jpg",
  "profile_tags": ["计算机", "效率控", "摄影"],
  "bio": "喜欢把通知系统做得更顺手一点。",
  "profile_updated_at": "2026-03-23T09:30:00.000Z",
  "is_vip": false,
  "vip_expired_at": null
}
```

### 当前占位行为

当前 backend 占位路由会回显收到的字段名：

```json
{
  "error": "个人资料接口已预留，暂未接入服务端持久化实现",
  "code": "profile_api_reserved",
  "reserved": true,
  "method": "PATCH",
  "path": "/api/user/profile",
  "accepted_fields": [
    "display_name",
    "profile_tags",
    "bio",
    "avatar_url",
    "profile_updated_at"
  ],
  "received_fields": [
    "bio",
    "display_name",
    "profile_tags",
    "profile_updated_at"
  ]
}
```

状态码：`501`

---

## 3. 上传头像

### 请求

```http
POST /user/profile/avatar
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

### 表单字段

- 字段名：`avatar`
- 文件类型：图片文件
- 推荐比例：1:1
- 推荐大小：压缩后不超过 1MB

### 目标响应结构

```json
{
  "avatar_url": "https://cdn.example.com/avatar/20240001.jpg"
}
```

### 当前占位行为

当前 backend 占位路由会返回表单约定说明：

```json
{
  "error": "个人资料接口已预留，暂未接入服务端持久化实现",
  "code": "profile_api_reserved",
  "reserved": true,
  "method": "POST",
  "path": "/api/user/profile/avatar",
  "accepted_content_type": "multipart/form-data",
  "accepted_field": "avatar",
  "received_file": "avatar.jpg"
}
```

状态码：`501`

---

## 4. 前端当前接入方式

当前前端模块的行为约定如下：

- 资料编辑保存时，优先写入本地 `user_profile`
- 默认不调用远端资料接口
- 若未来需要联调，只需设置环境变量：

```bash
EXPO_PUBLIC_PROFILE_REMOTE_SYNC=1
```

- 开启后前端会按以下顺序尝试同步：
  1. 如头像是新本地图片，先调用 `POST /user/profile/avatar`
  2. 再调用 `PATCH /user/profile` 更新昵称、标签、简介和头像 URL
  3. 若远端同步失败，前端不回滚本地资料

---

## 5. 推荐联调顺序

建议后端同伴按以下顺序补全：

1. 先实现 `PATCH /user/profile`
2. 再实现 `GET /user/profile`
3. 最后实现 `POST /user/profile/avatar`

这样前端可以先基于已有本地头像逻辑，最早完成昵称、标签和简介的远端同步联调。
