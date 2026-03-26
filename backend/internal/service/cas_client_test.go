package service

import (
	"io"
	"net/http"
	"strings"
	"testing"
)

func TestExtractNameFromProfile_UserNameClass(t *testing.T) {
	html := `<html><body><span class="user-name">张三</span></body></html>`
	got := extractNameFromProfile(html)
	if got != "张三" {
		t.Fatalf("expected 张三, got %q", got)
	}
}

func TestExtractNameFromProfile_NgBindingFallback(t *testing.T) {
	html := `<span ng-if="!isEditDisplayName" class="ng-scope ng-binding">李四</span>`
	got := extractNameFromProfile(html)
	if got != "李四" {
		t.Fatalf("expected 李四, got %q", got)
	}
}

func TestFetchProfileHTML_FollowsRedirect(t *testing.T) {
	client := &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			if req.URL.Path == "/default.aspx" {
				return &http.Response{
					StatusCode: http.StatusFound,
					Header:     http.Header{"Location": []string{"https://campus.local/home"}},
					Body:       io.NopCloser(strings.NewReader("")),
					Request:    req,
				}, nil
			}
			if req.URL.Path == "/home" {
				return &http.Response{
					StatusCode: http.StatusOK,
					Header:     make(http.Header),
					Body:       io.NopCloser(strings.NewReader(`<span class="user-name">王五</span>`)),
					Request:    req,
				}, nil
			}
			return &http.Response{
				StatusCode: http.StatusNotFound,
				Header:     make(http.Header),
				Body:       io.NopCloser(strings.NewReader("not found")),
				Request:    req,
			}, nil
		}),
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) > 10 {
				t.Fatalf("too many redirects")
			}
			return nil
		},
	}

	body, finalStatus, err := fetchProfileHTML(client, "https://campus.local/default.aspx")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if finalStatus != http.StatusOK {
		t.Fatalf("expected final status 200, got %d", finalStatus)
	}
	if extractNameFromProfile(body) != "王五" {
		t.Fatalf("expected extracted name 王五")
	}
}

type roundTripFunc func(req *http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return fn(req)
}
