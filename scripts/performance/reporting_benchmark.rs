//! Isolated canonical checkpoint/export measurement; fictional records only.
use serde_json::{Value, json};
use std::{fs, path::PathBuf, time::Instant};
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
    let args = std::env::args().collect::<Vec<_>>();
    let mut record: Value =
        serde_json::from_reader(std::io::BufReader::new(fs::File::open(&args[2])?))?;
    let output = PathBuf::from(&args[3]);
    fs::create_dir(&output)?;
    record["exports"] = Value::Null;
    let start_cpu = cpu();
    let start = Instant::now();
    match args[1].as_str() {
        "checkpoint" => immuknow::report::checkpoint(&output, &mut record)?,
        "publish" => immuknow::report::publish(&output, &mut record)?,
        _ => anyhow::bail!("expected checkpoint or publish"),
    }
    let wall = start.elapsed().as_secs_f64();
    let cpu = cpu() - start_cpu;
    let memory = fs::read_to_string("/proc/self/status")?
        .lines()
        .find(|line| line.starts_with("VmHWM:"))
        .unwrap_or("")
        .to_owned();
    println!(
        "{}",
        json!({"operation":args[1],"rows":record["entries"].as_array().unwrap().len(),"wall_seconds":wall,"cpu_seconds":cpu,"process_high_water_rss_including_record_load":memory,"record_bytes":fs::metadata(output.join("run.json"))?.len(),"exports":record["exports"]})
    );
    Ok(())
}
