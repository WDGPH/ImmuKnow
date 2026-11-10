//! Isolated actual public read_json benchmark; hash validation is outside timing.
use serde_json::{Value, json};
use std::{fs, path::Path, time::Instant};
#[repr(C)]
struct Timespec {
    seconds: i64,
    nanoseconds: i64,
}
unsafe extern "C" {
    fn clock_gettime(clock: i32, out: *mut Timespec) -> i32;
}
fn cpu() -> f64 {
    let mut value = Timespec {
        seconds: 0,
        nanoseconds: 0,
    };
    assert_eq!(unsafe { clock_gettime(2, &mut value) }, 0);
    value.seconds as f64 + value.nanoseconds as f64 / 1e9
}
fn main() -> anyhow::Result<()> {
    let input = std::env::args().nth(1).expect("path to fictional run.json");
    let start_cpu = cpu();
    let start = Instant::now();
    let record: Value = immuknow::read_json(Path::new(&input))?;
    let wall = start.elapsed().as_secs_f64();
    let cpu = cpu() - start_cpu;
    let memory = fs::read_to_string("/proc/self/status")?
        .lines()
        .find(|line| line.starts_with("VmHWM:"))
        .unwrap_or("")
        .to_owned();
    let rows = record["entries"].as_array().map_or(0, Vec::len);
    let content_sha256 = immuknow::hash(&serde_json::to_vec(&record)?);
    println!(
        "{}",
        json!({"operation":"public_read_json_Value","rows":rows,
        "wall_seconds":wall,"cpu_seconds":cpu,"read_high_water_rss":memory,
        "canonical_content_sha256":content_sha256})
    );
    Ok(())
}
