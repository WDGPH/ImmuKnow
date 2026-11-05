//! Small bounded work queue. Workers return receipts; only the caller edits the run record.
use anyhow::{Result, anyhow};
use std::{
    sync::{
        Arc, Mutex,
        mpsc::{self, Receiver, SyncSender},
    },
    thread,
};

pub fn with_pool<J: Send, R: Send, T>(
    workers: usize,
    work: impl Fn(J) -> R + Sync,
    body: impl FnOnce(SyncSender<J>, Receiver<R>) -> Result<T>,
) -> Result<T> {
    let (jobs, incoming) = mpsc::sync_channel::<J>(workers * 2);
    let incoming = Arc::new(Mutex::new(incoming));
    let (completed, results) = mpsc::channel();
    thread::scope(|scope| {
        let mut handles = Vec::new();
        for _ in 0..workers {
            let (incoming, work, completed) = (incoming.clone(), &work, completed.clone());
            handles.push(scope.spawn(move || {
                loop {
                    // Release the receiver lock before processing a document.
                    let job = incoming.lock().unwrap().recv();
                    let Ok(job) = job else { break };
                    if completed.send(work(job)).is_err() {
                        break;
                    }
                }
            }));
        }
        // Only workers retain the queue receiver. If they all panic, a blocked
        // producer sees disconnection instead of waiting forever.
        drop(incoming);
        drop(completed);
        // The body owns the sender and closes it before draining results. On an
        // early error it drops both channels; all workers still join before return.
        let result = body(jobs, results);
        let mut panicked = false;
        for handle in handles {
            panicked |= handle.join().is_err();
        }
        if panicked {
            return Err(anyhow!("PDF worker panicked"));
        }
        result
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn worker_panic_disconnects_a_full_queue() {
        let result = with_pool(
            1,
            |_: usize| -> () { panic!("expected worker failure") },
            |jobs, results| {
                for i in 0..16 {
                    jobs.send(i).map_err(|_| anyhow!("worker stopped"))?;
                }
                drop(jobs);
                for _ in results {}
                Ok(())
            },
        );
        assert!(result.unwrap_err().to_string().contains("worker panicked"));
    }
}
