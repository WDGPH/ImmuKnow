fn main() {
    // Refresh embedded bytes when a resource changes, including cached CI builds.
    println!("cargo:rerun-if-changed=resources");
}
