package handler

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestAIRequestQueue_ProcessesUpToMaxConcurrent(t *testing.T) {
	queue := NewAIRequestQueue(2)
	defer queue.Close()

	var running atomic.Int32
	var maxRunning atomic.Int32
	var completed atomic.Int32
	total := 6
	var wg sync.WaitGroup

	for i := 0; i < total; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			queue.Enqueue(context.Background(), func(ctx context.Context) {
				cur := running.Add(1)
				for {
					old := maxRunning.Load()
					if cur <= old || maxRunning.CompareAndSwap(old, cur) {
						break
					}
				}
				time.Sleep(50 * time.Millisecond) // simulate work
				running.Add(-1)
				completed.Add(1)
			})
		}()
	}
	wg.Wait()
	queue.WaitAll()

	if completed.Load() != int32(total) {
		t.Fatalf("expected %d completed, got %d", total, completed.Load())
	}
	if maxRunning.Load() > 2 {
		t.Fatalf("expected max concurrent <= 2, got %d", maxRunning.Load())
	}
}

func TestAIRequestQueue_ProcessesInFIFOOrder(t *testing.T) {
	queue := NewAIRequestQueue(1) // single worker ensures FIFO
	defer queue.Close()

	var order []int
	var mu sync.Mutex

	for i := 0; i < 5; i++ {
		i := i
		queue.Enqueue(context.Background(), func(ctx context.Context) {
			mu.Lock()
			order = append(order, i)
			mu.Unlock()
		})
	}

	queue.WaitAll()

	for i, v := range order {
		if v != i {
			t.Fatalf("expected order %d, got %d at index %d", i, v, i)
		}
	}
}

func TestAIRequestQueue_ContextCancellation(t *testing.T) {
	queue := NewAIRequestQueue(1)
	defer queue.Close()

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // immediately cancel

	executed := false
	queue.Enqueue(ctx, func(ctx context.Context) {
		executed = true
	})

	time.Sleep(50 * time.Millisecond)

	if executed {
		t.Fatal("expected task to be skipped due to context cancellation")
	}
}
