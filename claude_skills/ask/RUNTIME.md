# Async Ask

Use this only for `/ask`.

```bash
command ask "$TARGET" <<'EOF'
$MESSAGE
EOF
```

- Sender is inferred from the current CCB workspace.
- `TARGET=all` broadcasts.
- After submit, end the current turn.
