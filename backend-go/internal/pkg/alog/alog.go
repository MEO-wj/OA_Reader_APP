package alog

import (
	"log"
	"sync/atomic"
)

var authDebugEnabled atomic.Bool

func SetAuthDebug(enabled bool) {
	authDebugEnabled.Store(enabled)
}

func AuthDebugEnabled() bool {
	return authDebugEnabled.Load()
}

func Authf(format string, args ...any) {
	if !authDebugEnabled.Load() {
		return
	}
	log.Printf(format, args...)
}
