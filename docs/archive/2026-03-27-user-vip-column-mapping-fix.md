# User VIP Column Mapping Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent future schema creation from generating duplicate VIP columns by explicitly mapping the user model to `is_vip` and `vip_expired_at`.

**Architecture:** Keep the existing `User` domain field names (`IsVIP`, `VIPExpiredAt`) and bind them to stable database column names with explicit GORM tags. Add a focused model test that verifies GORM resolves the expected column names, so future refactors cannot silently reintroduce `is_v_ip` / `v_ip_expired_at`.

**Tech Stack:** Go 1.21, GORM, PostgreSQL, Go testing

---

### Task 1: Lock down GORM column names with a failing test

**Files:**
- Modify: `backend/internal/model/user_profile_fields_test.go`
- Test: `backend/internal/model/user_profile_fields_test.go`

**Step 1: Write the failing test**

Add a test that parses `model.User` with GORM schema metadata and asserts:

- `IsVIP` maps to `is_vip`
- `VIPExpiredAt` maps to `vip_expired_at`

**Step 2: Run test to verify it fails**

Run: `go test ./internal/model -run 'TestUserModel_(ContainsProfileFields|VIPFieldsUseStableColumnNames)$'`
Expected: FAIL because GORM currently resolves `is_v_ip` / `v_ip_expired_at`

### Task 2: Apply the minimal model fix

**Files:**
- Modify: `backend/internal/model/user.go`
- Test: `backend/internal/model/user_profile_fields_test.go`

**Step 3: Write minimal implementation**

Add explicit GORM column tags:

- `IsVIP bool 'gorm:"column:is_vip;not null;default:false"'`
- `VIPExpiredAt *time.Time 'gorm:"column:vip_expired_at"'`

**Step 4: Run test to verify it passes**

Run: `go test ./internal/model -run 'TestUserModel_(ContainsProfileFields|VIPFieldsUseStableColumnNames)$'`
Expected: PASS

### Task 3: Verify no regression in related behavior

**Files:**
- Verify existing tests only

**Step 5: Run related tests**

Run: `go test ./internal/service ./internal/model`
Expected: PASS
