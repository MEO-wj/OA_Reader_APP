package handler

import (
	"context"
	"sync"
)

type queuedRequest struct {
	ctx     context.Context
	execute func(ctx context.Context)
	done    chan struct{}
}

// AIRequestQueue is a FIFO queue with max concurrency control (channel-based worker pool).
// It ensures no more than maxConcurrent tasks execute simultaneously.
type AIRequestQueue struct {
	ch      chan *queuedRequest
	workers int
	wg      sync.WaitGroup // tracks worker goroutines
	enqWG   sync.WaitGroup // tracks in-flight Enqueue calls
	mu      sync.Mutex     // protects closed flag and channel send
	closed  bool
}

// NewAIRequestQueue creates a new AIRequestQueue with the given max concurrency.
func NewAIRequestQueue(maxConcurrent int) *AIRequestQueue {
	q := &AIRequestQueue{
		ch:      make(chan *queuedRequest, 50),
		workers: maxConcurrent,
	}
	for i := 0; i < q.workers; i++ {
		q.wg.Add(1)
		go q.worker()
	}
	return q
}

func (q *AIRequestQueue) worker() {
	defer q.wg.Done()
	for req := range q.ch {
		select {
		case <-req.ctx.Done():
			close(req.done)
		default:
			req.execute(req.ctx)
			close(req.done)
		}
	}
}

// Enqueue adds a task to the queue and returns a channel that is closed when
// the task completes or is skipped.
func (q *AIRequestQueue) Enqueue(ctx context.Context, execute func(ctx context.Context)) <-chan struct{} {
	done := make(chan struct{})
	q.enqWG.Add(1)

	q.mu.Lock()
	if q.closed {
		q.mu.Unlock()
		q.enqWG.Done()
		close(done)
		return done
	}
	q.ch <- &queuedRequest{ctx: ctx, execute: execute, done: done}
	q.mu.Unlock()

	q.enqWG.Done()
	return done
}

// WaitAll blocks until all in-flight Enqueue calls have submitted their tasks,
// then processes all remaining items and waits for workers to finish.
func (q *AIRequestQueue) WaitAll() {
	q.enqWG.Wait() // wait for all Enqueue calls to finish submitting
	q.mu.Lock()
	q.closed = true
	q.mu.Unlock()
	close(q.ch) // safe: mu guarantees no more sends
	q.wg.Wait()
}

// Close immediately stops accepting new items and signals workers to stop.
// Pending items in the queue may not be processed.
func (q *AIRequestQueue) Close() {
	q.mu.Lock()
	if q.closed {
		q.mu.Unlock()
		return
	}
	q.closed = true
	q.mu.Unlock()
	close(q.ch)
	q.wg.Wait()
}
