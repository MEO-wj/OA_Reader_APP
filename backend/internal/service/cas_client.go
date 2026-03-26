package service

import (
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/oap/backend-go/internal/pkg/alog"
)

const (
	defaultServiceURL     = "https://netms.stu.edu.cn/default.aspx"
	defaultLoginURLPrefix = "https://sso.stu.edu.cn/login?service="
	defaultTimeout        = 10 * time.Second
)

var (
	campusLoginURL   = defaultLoginURLPrefix + url.QueryEscape(defaultServiceURL)
	campusServiceURL = defaultServiceURL
	campusTimeout    = defaultTimeout
)

type casResponse struct {
	session *http.Client
	ticket  string
}

func extractHiddenInputs(html string) map[string]string {
	result := make(map[string]string)
	pattern := regexp.MustCompile(`<input\s+[^>]*type\s*=\s*["']?hidden["']?[^>]*>`)
	matches := pattern.FindAllString(html, -1)

	for _, tag := range matches {
		nameMatch := regexp.MustCompile(`name\s*=\s*["']([^"']+)["']`).FindStringSubmatch(tag)
		valueMatch := regexp.MustCompile(`value\s*=\s*["']([^"']*)["']`).FindStringSubmatch(tag)
		if len(nameMatch) > 1 {
			value := ""
			if len(valueMatch) > 1 {
				value = valueMatch[1]
			}
			result[nameMatch[1]] = value
		}
	}
	return result
}

func extractFormAction(html string) string {
	pattern := regexp.MustCompile(`<form\s+[^>]*id\s*=\s*["']?fm1["']?[^>]*>`)
	match := pattern.FindString(html)
	if match == "" {
		return ""
	}
	actionMatch := regexp.MustCompile(`action\s*=\s*["']([^"']+)["']`).FindStringSubmatch(match)
	if len(actionMatch) > 1 {
		return actionMatch[1]
	}
	return ""
}

func extractTicketFromLocation(location string) string {
	if location == "" {
		return ""
	}
	if strings.Contains(location, "ticket=") {
		parsed, err := url.Parse(location)
		if err == nil {
			tickets, _ := url.ParseQuery(parsed.RawQuery)
			if t := tickets.Get("ticket"); strings.HasPrefix(t, "ST-") {
				return t
			}
		}
	}
	return ""
}

func extractTicketFromBody(body []byte) string {
	// 1. 先尝试 meta refresh
	metaPattern := regexp.MustCompile(`<meta\s+[^>]*http-equiv\s*=\s*["']?refresh["']?[^>]*>`)
	metaMatch := metaPattern.Find(body)
	if metaMatch != nil {
		contentMatch := regexp.MustCompile(`content\s*=\s*["']([^"']+)["']`).FindSubmatch(metaMatch)
		if len(contentMatch) > 1 {
			content := string(contentMatch[1])
			if strings.Contains(content, "ticket=") {
				ticketPart := strings.Split(content, "ticket=")[1]
				ticketPart = strings.Split(ticketPart, ";")[0]
				ticketPart = strings.TrimSpace(ticketPart)
				if strings.HasPrefix(ticketPart, "ST-") {
					return ticketPart
				}
			}
		}
	}
	// 2. 直接从 body 找 ST-
	ticketMatch := regexp.MustCompile(`ST-[A-Za-z0-9\-]+`).Find(body)
	if ticketMatch != nil {
		return string(ticketMatch)
	}
	return ""
}

func casLogin(client *http.Client, loginURL, username, password string) (*casResponse, error) {
	alog.Authf("[CAS][login] start username=%q login_url=%q", username, loginURL)
	// 1. 获取登录页面
	resp, err := client.Get(loginURL)
	if err != nil {
		alog.Authf("[CAS][login] fetch login page failed username=%q err=%v", username, err)
		return nil, fmt.Errorf("failed to fetch login page: %w", err)
	}
	defer resp.Body.Close()
	alog.Authf("[CAS][login] fetched login page username=%q status=%d final_url=%q", username, resp.StatusCode, resp.Request.URL.String())

	html, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read login page: %w", err)
	}
	htmlStr := string(html)

	// 记录最终 URL（可能因重定向而改变）
	baseURL := resp.Request.URL.String()

	// 2. 提取 hidden 字段和 form action
	hidden := extractHiddenInputs(htmlStr)
	action := extractFormAction(htmlStr)
	alog.Authf("[CAS][login] parsed login form username=%q hidden_fields=%d action=%q", username, len(hidden), action)

	// 3. 构造提交 URL（使用 urljoin 处理相对路径）
	submitURL := action
	if submitURL == "" {
		submitURL = baseURL
	} else if !strings.HasPrefix(submitURL, "http") {
		// 相对路径，需要与 baseURL 合并
		parsedBase, _ := url.Parse(baseURL)
		parsedAction, _ := url.Parse(submitURL)
		submitURL = parsedBase.ResolveReference(parsedAction).String()
	}

	// 4. 构造登录请求
	formData := url.Values{}
	for k, v := range hidden {
		formData.Set(k, v)
	}
	formData.Set("username", username)
	formData.Set("password", password)
	if _, ok := formData["_eventId"]; !ok {
		formData.Set("_eventId", "submit")
	}
	if _, ok := formData["execution"]; !ok {
		formData.Set("execution", "e1s1")
	}

	// 5. 提交登录（POST，不自动跟随重定向）
	req, err := http.NewRequest("POST", submitURL, strings.NewReader(formData.Encode()))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Referer", baseURL)

	resp, err = client.Do(req)
	if err != nil {
		alog.Authf("[CAS][login] submit login failed username=%q err=%v", username, err)
		return nil, fmt.Errorf("failed to submit login: %w", err)
	}
	defer resp.Body.Close()
	alog.Authf("[CAS][login] submitted login username=%q status=%d location=%q", username, resp.StatusCode, resp.Header.Get("Location"))

	// 6. 从响应中提取 ticket
	body, _ := io.ReadAll(resp.Body)
	ticket := extractTicketFromLocation(resp.Header.Get("Location"))
	if ticket == "" {
		ticket = extractTicketFromBody(body)
	}
	alog.Authf("[CAS][login] ticket extraction username=%q ticket_found=%t", username, ticket != "")

	// 7. 如果是重定向，跟随重定向
	if ticket == "" && resp.StatusCode >= 300 && resp.StatusCode < 400 {
		redirectURL := resp.Header.Get("Location")
		if redirectURL != "" {
			// 构造完整 URL
			if !strings.HasPrefix(redirectURL, "http") {
				parsedBase, _ := url.Parse(submitURL)
				if strings.HasPrefix(redirectURL, "/") {
					redirectURL = parsedBase.Scheme + "://" + parsedBase.Host + redirectURL
				} else {
					redirectURL = parsedBase.ResolveReference(&url.URL{Path: redirectURL}).String()
				}
			}
			// 使用 Get 自动跟随重定向
			redirectResp, err := client.Get(redirectURL)
			if err == nil {
				defer redirectResp.Body.Close()
				alog.Authf("[CAS][login] follow redirect username=%q status=%d redirect_url=%q", username, redirectResp.StatusCode, redirectResp.Request.URL.String())
				redirectBody, _ := io.ReadAll(redirectResp.Body)
				ticket = extractTicketFromLocation(redirectResp.Header.Get("Location"))
				if ticket == "" {
					ticket = extractTicketFromBody(redirectBody)
				}
				// 如果 URL 本身包含 ticket
				if ticket == "" {
					ticket = extractTicketFromLocation(redirectResp.Request.URL.String())
				}
			}
		}
	}

	if ticket == "" {
		alog.Authf("[CAS][login] no ticket received username=%q", username)
		return nil, fmt.Errorf("CAS login failed: no ticket received")
	}
	alog.Authf("[CAS][login] success username=%q ticket_prefix=%q", username, ticketPrefix(ticket))

	return &casResponse{
		session: client,
		ticket:  ticket,
	}, nil
}

func validateTicket(client *http.Client, serviceURL, ticket string) bool {
	validateURL := fmt.Sprintf("%s?ticket=%s", serviceURL, ticket)
	alog.Authf("[CAS][validate] request url=%q ticket_prefix=%q", validateURL, ticketPrefix(ticket))
	req, _ := http.NewRequest("GET", validateURL, nil)
	resp, err := client.Do(req)
	if err != nil {
		alog.Authf("[CAS][validate] request failed err=%v", err)
		return false
	}
	defer resp.Body.Close()
	alog.Authf("[CAS][validate] response status=%d location=%q", resp.StatusCode, resp.Header.Get("Location"))
	// CAS 验证成功会返回 200，或者返回重定向到 service
	return resp.StatusCode == 200 || resp.StatusCode == 302 || resp.StatusCode == 303
}

// extractNameFromProfile 从用户信息页面提取姓名
// 页面结构: <span style="font-size: 24px;" ng-if="!isEditDisplayName" class="ng-scope ng-binding">黄应辉</span>
func extractNameFromProfile(html string) string {
	// Python 端优先提取 <span class="user-name">姓名</span>
	userNamePattern := regexp.MustCompile(`<span[^>]*class=["'][^"']*\buser-name\b[^"']*["'][^>]*>([^<]+)</span>`)
	userNameMatches := userNamePattern.FindStringSubmatch(html)
	if len(userNameMatches) > 1 {
		return strings.TrimSpace(userNameMatches[1])
	}

	// 匹配包含 ng-if="!isEditDisplayName" 和 class="ng-scope ng-binding" 的 span
	// 并获取其文本内容
	pattern := regexp.MustCompile(`<span[^>]*ng-if=["']?!isEditDisplayName["'][^>]*class=["']?ng-scope ng-binding["']?[^>]*>([^<]+)</span>`)
	matches := pattern.FindStringSubmatch(html)
	if len(matches) > 1 {
		return strings.TrimSpace(matches[1])
	}
	return ""
}

// casLoginAndGetName 执行 CAS 登录并获取用户真实姓名
func casLoginAndGetName(username, password string) (string, error) {
	alog.Authf("[CAS][flow] begin username=%q login_url=%q service_url=%q timeout=%s", username, campusLoginURL, campusServiceURL, campusTimeout)
	// 创建 cookie jar
	jar, _ := cookiejar.New(nil)
	client := &http.Client{
		Jar:     jar,
		Timeout: campusTimeout,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			// 不自动跟随重定向，手动处理
			return http.ErrUseLastResponse
		},
	}

	// 1. CAS 登录获取 ticket
	result, err := casLogin(client, campusLoginURL, username, password)
	if err != nil {
		alog.Authf("[CAS][flow] login failed username=%q err=%v", username, err)
		return "", err
	}

	// 2. 验证 ticket
	if !validateTicket(client, campusServiceURL, result.ticket) {
		alog.Authf("[CAS][flow] validate ticket failed username=%q ticket_prefix=%q", username, ticketPrefix(result.ticket))
		return "", fmt.Errorf("ticket validation failed")
	}
	alog.Authf("[CAS][flow] validate ticket success username=%q", username)

	// 3. 访问用户信息页面获取真实姓名
	body, finalStatus, err := fetchProfileHTML(client, campusServiceURL)
	if err != nil {
		alog.Authf("[CAS][flow] fetch profile failed username=%q err=%v", username, err)
		return "", fmt.Errorf("failed to fetch profile page: %w", err)
	}
	alog.Authf("[CAS][flow] fetched profile username=%q status=%d", username, finalStatus)

	userName := extractNameFromProfile(body)
	if userName == "" {
		alog.Authf("[CAS][flow] profile name empty, fallback username=%q", username)
		return username, nil // 提取失败则用 username 作为 displayName
	}
	alog.Authf("[CAS][flow] success username=%q display_name=%q", username, userName)
	return userName, nil
}

func ticketPrefix(ticket string) string {
	if len(ticket) <= 12 {
		return ticket
	}
	return ticket[:12] + "..."
}

func fetchProfileHTML(client *http.Client, serviceURL string) (string, int, error) {
	jar := client.Jar
	followClient := &http.Client{
		Jar:       jar,
		Timeout:   campusTimeout,
		Transport: client.Transport,
	}

	resp, err := followClient.Get(serviceURL)
	if err != nil {
		return "", 0, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", resp.StatusCode, err
	}
	return string(body), resp.StatusCode, nil
}
