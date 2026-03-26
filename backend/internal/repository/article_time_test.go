package repository

import (
	"testing"
	"time"
)

func TestLocalDayStart_UsesLocalCalendarBoundary(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("load location: %v", err)
	}

	now := time.Date(2026, 3, 19, 7, 30, 0, 0, time.UTC)
	start := localDayStart(now, loc)

	expected := time.Date(2026, 3, 19, 0, 0, 0, 0, loc)
	if !start.Equal(expected) {
		t.Fatalf("expected %v, got %v", expected, start)
	}
}

func TestLocalDayRange_CoversWholeLatestDay(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("load location: %v", err)
	}

	latest := time.Date(2026, 3, 18, 15, 59, 59, 0, time.UTC) // Asia/Shanghai: 23:59:59
	start, next := localDayRange(latest, loc)

	expectedStart := time.Date(2026, 3, 18, 0, 0, 0, 0, loc)
	expectedNext := time.Date(2026, 3, 19, 0, 0, 0, 0, loc)
	if !start.Equal(expectedStart) {
		t.Fatalf("expected day start %v, got %v", expectedStart, start)
	}
	if !next.Equal(expectedNext) {
		t.Fatalf("expected next day %v, got %v", expectedNext, next)
	}
}
