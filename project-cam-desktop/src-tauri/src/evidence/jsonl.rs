use serde_json::Value;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

pub struct ParsedJsonl {
    pub values: Vec<Value>,
    pub rejected: usize,
    pub truncated: bool,
}

pub fn read_jsonl_tail(path: &Path, max_bytes: u64) -> Result<ParsedJsonl, String> {
    let mut input =
        File::open(path).map_err(|error| format!("open {}: {error}", path.display()))?;
    let len = input
        .metadata()
        .map_err(|error| format!("stat {}: {error}", path.display()))?
        .len();
    let limit = max_bytes.max(1);
    let start = len.saturating_sub(limit);
    let starts_mid_line = if start > 0 {
        input
            .seek(SeekFrom::Start(start - 1))
            .map_err(|error| format!("seek {}: {error}", path.display()))?;
        let mut previous = [0u8; 1];
        input
            .read_exact(&mut previous)
            .map_err(|error| format!("read boundary {}: {error}", path.display()))?;
        previous[0] != b'\n'
    } else {
        false
    };
    input
        .seek(SeekFrom::Start(start))
        .map_err(|error| format!("seek {}: {error}", path.display()))?;

    let mut bytes = Vec::with_capacity(limit.min(usize::MAX as u64) as usize);
    input
        .take(limit)
        .read_to_end(&mut bytes)
        .map_err(|error| format!("read {}: {error}", path.display()))?;

    let payload = if starts_mid_line {
        match bytes.iter().position(|byte| *byte == b'\n') {
            Some(end) => &bytes[end + 1..],
            None => &[],
        }
    } else {
        bytes.as_slice()
    };

    let mut values = Vec::new();
    let mut rejected = 0;
    for line in String::from_utf8_lossy(payload).lines() {
        if line.trim().is_empty() {
            continue;
        }
        match serde_json::from_str::<Value>(line) {
            Ok(value @ Value::Object(_)) => values.push(value),
            Ok(_) | Err(_) => rejected += 1,
        }
    }
    Ok(ParsedJsonl {
        values,
        rejected,
        truncated: start > 0,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;
    use uuid::Uuid;

    fn test_dir() -> PathBuf {
        let root = std::env::temp_dir().join(format!("project-cam-jsonl-test-{}", Uuid::new_v4()));
        fs::create_dir_all(&root).unwrap();
        root
    }

    #[test]
    fn bounded_tail_drops_a_truncated_first_line_and_counts_bad_json() {
        let root = test_dir();
        let path = root.join("large.jsonl");
        let prefix = format!("{}\n", serde_json::json!({"old": "x".repeat(300)}));
        let valid = format!("{}\n", serde_json::json!({"keep": 1}));
        fs::write(&path, format!("{prefix}not-json\n{valid}")).unwrap();
        let parsed = read_jsonl_tail(&path, 128).unwrap();
        assert_eq!(parsed.values, vec![serde_json::json!({"keep": 1})]);
        assert_eq!(parsed.rejected, 1);
        assert!(parsed.truncated);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn non_finite_json_tokens_are_rejected() {
        let root = test_dir();
        let path = root.join("bad.jsonl");
        fs::write(&path, "{\"value\": NaN}\n{\"value\": 3.0}\n").unwrap();
        let parsed = read_jsonl_tail(&path, 1024).unwrap();
        assert_eq!(parsed.values.len(), 1);
        assert_eq!(parsed.rejected, 1);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn exact_line_boundary_keeps_the_first_complete_tail_record() {
        let root = test_dir();
        let path = root.join("boundary.jsonl");
        let old = format!("{}\n", serde_json::json!({"old": 0}));
        let tail = format!(
            "{}\n{}\n",
            serde_json::json!({"keep": 1}),
            serde_json::json!({"keep": 2})
        );
        fs::write(&path, format!("{old}{tail}")).unwrap();

        let parsed = read_jsonl_tail(&path, tail.len() as u64).unwrap();
        assert_eq!(
            parsed.values,
            vec![
                serde_json::json!({"keep": 1}),
                serde_json::json!({"keep": 2})
            ]
        );
        assert!(parsed.truncated);
        fs::remove_dir_all(root).unwrap();
    }
}
