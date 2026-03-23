# 个人中心个性化资料功能实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在个人中心中实现可编辑的个性化资料能力，支持修改名字、上传头像、设置个性化标签和个人简介，并保持本地优先保存与后续服务端同步预留

**Architecture:** 本地优先存储个人资料；个人中心作为展示页，新增独立编辑页 `/(tabs)/settings/profile-edit`；用户保存后立即回写本地 `user_profile` 并刷新展示，未来可无缝接入服务端同步

**Tech Stack:** Expo Router, React Native, Expo Secure Store, Expo Image Picker, TypeScript

---

## Task 1: 基线检查当前个人中心与资料存储现状

**Files:**
- Inspect: `OAP-app/app/(tabs)/settings/index.tsx`
- Inspect: `OAP-app/hooks/use-user-profile.ts`
- Inspect: `OAP-app/storage/auth-storage.ts`

**Step 1: 确认个人中心当前只展示基础昵称信息**

```bash
cd OA-Reader/OAP-app
rg -n "displayName =|TopBar variant=\"explore\"|profileBlock|avatarRing|profileName" app/(tabs)/settings/index.tsx
```

**Step 2: 确认当前 UserProfile 结构只包含基础字段**

```bash
cd OA-Reader/OAP-app
rg -n "type UserProfile|display_name|username|is_vip|vip_expired_at" hooks/use-user-profile.ts
```

**Step 3: 确认资料仍存储在 `user_profile`**

```bash
cd OA-Reader/OAP-app
rg -n "USER_PROFILE_KEY|getUserProfileRaw|setUserProfileRaw" storage/auth-storage.ts
```

**预期:** 当前个人中心没有头像上传、标签编辑、个人简介编辑能力，资料结构也尚未承载这些字段

---

## Task 2: 扩展 UserProfile 与本地存储结构

**Files:**
- Modify: `OAP-app/hooks/use-user-profile.ts`
- Modify: `OAP-app/storage/auth-storage.ts`

**Step 1: 扩展 `UserProfile` 类型**

在 `hooks/use-user-profile.ts` 中补充以下字段:

```ts
type UserProfile = {
  display_name?: string;
  username?: string;
  is_vip?: boolean;
  vip_expired_at?: string;
  avatar_url?: string;
  avatar_local_uri?: string;
  profile_tags?: string[];
  bio?: string;
  profile_updated_at?: string;
};
```

**Step 2: 保持 `user_profile` 作为唯一的本地资料存储入口**

`storage/auth-storage.ts` 不新增新的 key，继续复用:

```ts
const USER_PROFILE_KEY = 'user_profile';
```

保存策略保持为整对象读写，避免昵称、头像、标签、简介拆散到多个存储键

**Step 3: 为后续编辑页准备资料更新辅助方法**

在 `storage/auth-storage.ts` 中新增一个资料合并更新方法，语义类似:

```ts
export async function updateUserProfile(patch: Partial<UserProfile>) {
  // 读取 user_profile
  // 合并 patch
  // 写回 user_profile
}
```

**Step 4: 确认旧数据兼容**

旧的 `user_profile` 只有 `display_name` 和 `username` 时，新字段应允许缺省，不影响登录后展示

**预期:** 个人资料结构升级后，仍兼容现有用户登录态和本地缓存

---

## Task 3: 改造个人中心资料展示卡并落地美术设计

**Files:**
- Modify: `OAP-app/app/(tabs)/settings/index.tsx`

**Step 1: 将个人中心顶部资料区升级为完整资料卡**

在现有头像和昵称基础上补充:
- 头像图片区
- 昵称
- 标签行
- 个人简介摘要
- `编辑资料` 主按钮

资料展示顺序固定为:

```text
头像
昵称
标签胶囊行
两行简介摘要 / 默认占位文案
编辑资料按钮
```

**Step 2: 保留并强化当前页面美术语言**

展示页视觉要求固定为:
- 延续现有深色氛围背景与柔光圆斑
- 头像外环继续使用金棕渐变高光
- 主资料卡采用玻璃拟态白色/半透明卡片
- 标签使用圆角胶囊样式
- `编辑资料` 按钮保持金棕强调色

**Step 3: 定义关键视觉细节**

```text
背景: 保留 AmbientBackground explore 风格，不新增新主题
头像: 104x104，4px 金棕渐变外环，无头像时显示首字母
资料卡: 圆角 32，轻阴影，边框保持浅金/浅白弱描边
标签胶囊: 高度 28，左右内边距 12，最多两行展示
简介: 默认展示 2 行，超出省略
按钮: 高度 48，圆角 18，支持按压态
```

**Step 4: 增加空状态文案**

当用户未设置对应资料时，展示:

```text
头像: 首字母默认态
标签: “添加你的第一个标签”
简介: “这个人很低调，还没有留下简介”
```

**Step 5: 绑定编辑入口**

`编辑资料` 按钮点击后跳转到:

```ts
router.push('/(tabs)/settings/profile-edit')
```

**预期:** 用户进入个人中心时，能直接看到更完整、更具展示性的个人资料卡，视觉风格与当前页面保持连续

---

## Task 4: 新增独立编辑页与路由

**Files:**
- Modify: `OAP-app/app/(tabs)/settings/_layout.tsx`
- Create: `OAP-app/app/(tabs)/settings/profile-edit.tsx`

**Step 1: 新增独立编辑页面**

创建:

```bash
cd OA-Reader/OAP-app
touch app/(tabs)/settings/profile-edit.tsx
```

**Step 2: 页面结构固定为单页编辑流**

编辑页内容顺序固定为:

```text
顶部栏（返回 + 标题）
头像编辑区域
昵称输入框
标签选择区
自定义标签输入区
简介输入框
保存按钮
```

**Step 3: 保持与现有 settings 路由一致**

`app/(tabs)/settings/_layout.tsx` 继续使用 `Stack screenOptions={{ headerShown: false }}`，新页面沿用现有栈式导航结构，不额外定制 header

**Step 4: 明确离开页行为**

如果用户修改后未保存就返回，需要弹出离开确认，文案建议:

```text
你有未保存的资料修改，确定离开吗？
```

**Step 5: 明确保存成功后的回流**

保存成功后执行:

```ts
router.back()
```

并让个人中心重新读取最新资料

**预期:** 编辑行为与展示行为分离，个人中心页面保持干净，编辑路径清晰

---

## Task 5: 实现头像选择、预览、替换与默认态

**Files:**
- Modify: `OAP-app/package.json`
- Modify: `OAP-app/app/(tabs)/settings/profile-edit.tsx`
- Modify: `OAP-app/app/(tabs)/settings/index.tsx`
- Modify: `OAP-app/hooks/use-user-profile.ts`

**Step 1: 补充头像选择依赖**

在 `package.json` 中新增:

```json
"expo-image-picker": "~17.0.8"
```

版本以当前 Expo SDK 54 兼容版本为准

**Step 2: 在编辑页实现相册选择流程**

编辑页头像区点击后执行:
- 请求媒体库权限
- 打开系统相册
- 仅允许图片
- 优先启用 1:1 裁剪
- 用户选中后立即本地预览

伪代码流程:

```ts
const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
const result = await ImagePicker.launchImageLibraryAsync({
  mediaTypes: ['images'],
  allowsEditing: true,
  aspect: [1, 1],
  quality: 0.8,
});
```

**Step 3: 定义头像数据来源优先级**

展示优先级固定为:

```text
avatar_local_uri > avatar_url > 首字母默认头像
```

**Step 4: 支持替换头像**

编辑页头像区提供一个明确的辅助文案:

```text
点击更换头像
```

已选头像再次点击时仍走替换流程，不需要二级菜单

**Step 5: 处理取消和失败场景**

需要覆盖:
- 用户拒绝相册权限
- 用户打开相册后取消
- 图片读取失败

这些场景不应清空当前头像，只给出轻提示

**预期:** 用户可在编辑页完成头像选择并立即看到预览效果，回到个人中心后头像同步更新

---

## Task 6: 实现昵称输入与校验

**Files:**
- Modify: `OAP-app/app/(tabs)/settings/profile-edit.tsx`
- Modify: `OAP-app/app/(tabs)/settings/index.tsx`
- Modify: `OAP-app/hooks/use-user-profile.ts`

**Step 1: 新增昵称输入组件**

编辑页提供单行输入框:

```text
标题: 昵称
占位: 请输入你的名字
```

**Step 2: 固定输入规则**

昵称规则固定为:
- 自动 `trim`
- 长度 2 到 20 字
- 不允许纯空格
- 保存时若为空则报错

**Step 3: 保存前校验**

伪代码:

```ts
const nextName = displayNameInput.trim();

if (!nextName || nextName.length < 2 || nextName.length > 20) {
  // 提示用户昵称长度不合法
}
```

**Step 4: 展示页使用统一回退逻辑**

个人中心昵称展示顺序固定为:

```text
display_name > username > 用户
```

**Step 5: 兼容默认头像首字母**

昵称更新后，首字母默认头像也要同步变化

**预期:** 用户可稳定修改昵称，且无论是否设置头像，昵称都能作为展示页的主要身份标识

---

## Task 7: 实现“预设 + 自定义”标签编辑

**Files:**
- Modify: `OAP-app/app/(tabs)/settings/profile-edit.tsx`
- Modify: `OAP-app/app/(tabs)/settings/index.tsx`
- Modify: `OAP-app/hooks/use-user-profile.ts`

**Step 1: 设计预设标签池**

编辑页先提供一组可直接点击的预设标签，例如:

```ts
const PRESET_TAGS = [
  '计算机',
  '自动化',
  '设计',
  '摄影',
  '阅读',
  '效率控',
  '社团人',
  '夜猫子',
];
```

**Step 2: 允许补充自定义标签**

在预设标签区下方增加自定义输入:

```text
占位: 输入自定义标签后添加
```

添加后立即生成一个胶囊标签

**Step 3: 固定标签规则**

标签规则固定为:
- 最多 5 个
- 单个标签长度 2 到 10 字
- 自动去重
- 点击已选标签可删除

**Step 4: 展示页标签样式**

个人中心展示页:
- 最多展示两行标签
- 超出不再展开
- 使用胶囊样式，背景色比主卡略深或略亮

**Step 5: 定义无标签状态**

当 `profile_tags` 为空时，展示引导占位:

```text
添加你的第一个标签
```

**预期:** 标签既能保持统一视觉，又允许用户表达一定个性

---

## Task 8: 实现个人简介输入、字数限制与展示折叠

**Files:**
- Modify: `OAP-app/app/(tabs)/settings/profile-edit.tsx`
- Modify: `OAP-app/app/(tabs)/settings/index.tsx`
- Modify: `OAP-app/hooks/use-user-profile.ts`

**Step 1: 在编辑页新增简介输入区**

输入区配置:
- 多行输入
- 显示当前字数
- 支持回车换行

文案建议:

```text
标题: 个人简介
占位: 用一句话介绍你自己
```

**Step 2: 固定简介规则**

简介规则固定为:
- 最多 80 字
- 允许为空
- 保存前自动 trim 首尾空白

**Step 3: 展示页折叠策略**

个人中心简介展示:
- 有内容时最多展示 2 行
- 超出使用省略
- 无内容时显示默认文案

**Step 4: 编辑页实时反馈字数**

例如:

```text
24 / 80
```

输入超限时禁用保存按钮或直接阻止继续输入，二选一时优先阻止继续输入

**预期:** 用户可以补充简短自我介绍，展示页在不增加过多阅读压力的前提下体现个性化

---

## Task 9: 实现本地优先保存、返回刷新与远端同步预留

**Files:**
- Modify: `OAP-app/storage/auth-storage.ts`
- Modify: `OAP-app/hooks/use-user-profile.ts`
- Modify: `OAP-app/app/(tabs)/settings/profile-edit.tsx`
- Modify: `OAP-app/app/(tabs)/settings/index.tsx`

**Step 1: 保存时统一写回完整资料对象**

保存时合并以下字段:

```ts
{
  display_name,
  avatar_local_uri,
  avatar_url,
  profile_tags,
  bio,
  profile_updated_at,
}
```

**Step 2: 以本地成功为主**

保存按钮流程固定为:
- 执行前端校验
- 写入 `user_profile`
- 更新 `profile_updated_at`
- 返回个人中心
- 触发个人中心重新读取资料

**Step 3: 解决 `useUserProfile` 仅首次加载的问题**

当前 `useUserProfile` 只在挂载时读取一次，本任务需要让它支持在返回页面后刷新。可选实现方向固定为其一:
- 页面 focus 时重新读取
- 增加手动 `reload` 能力

优先推荐让 hook 返回:

```ts
const { profile, reloadProfile } = useUserProfile();
```

**Step 4: 为未来服务端同步预留接口语义**

本期不接真实接口，但代码与文档需要预留未来能力:

```text
GET /user/profile
PATCH /user/profile
POST /user/profile/avatar
```

失败策略固定为:
- 本地写入成功即视为保存成功
- 未来若远端同步失败，只做提示，不回滚本地资料

**Step 5: 增加保存中的交互状态**

保存按钮需要有:
- 默认态
- 保存中 disabled 态
- 保存成功后返回

**预期:** 用户修改资料后能立即看到效果，且当前实现不依赖后端接口即可成立

---

## Task 10: 执行 lint 与手工验证清单

**Files:**
- Verify: `OAP-app/package.json`
- Verify: `OAP-app/app/(tabs)/settings/index.tsx`
- Verify: `OAP-app/app/(tabs)/settings/_layout.tsx`
- Verify: `OAP-app/app/(tabs)/settings/profile-edit.tsx`
- Verify: `OAP-app/hooks/use-user-profile.ts`
- Verify: `OAP-app/storage/auth-storage.ts`

**Step 1: 安装新依赖**

```bash
cd OA-Reader/OAP-app
npx expo install expo-image-picker
```

**Step 2: 运行 lint**

```bash
cd OA-Reader/OAP-app
npm run lint
```

**Step 3: 手工验证个人中心展示**

验证以下场景:
- 默认首字母头像正常显示
- 已设置头像时显示本地头像
- 昵称更新后个人中心立即刷新
- 标签为空时显示占位文案
- 标签较多时最多展示两行
- 简介为空和有内容两种状态均正常

**Step 4: 手工验证编辑页流程**

验证以下场景:
- 进入 `/(tabs)/settings/profile-edit` 正常
- 头像可从相册选择并预览
- 相册权限拒绝后提示正常
- 昵称长度校验正常
- 标签添加、删除、去重、上限校验正常
- 简介字数限制正常
- 未保存返回时出现确认提示
- 保存中不可重复点击

**Step 5: 验证本地持久化**

验证以下场景:
- 保存后退出应用重新进入，资料仍保留
- 登录态不丢失
- 旧用户资料对象缺失新字段时不报错

**预期:** lint 通过，资料编辑与展示链路完整，个性化功能可在个人中心稳定使用

