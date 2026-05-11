Use this only for `/ask <target> <message...>`.

- `TARGET` = first token; `MESSAGE` = raw remainder, forwarded verbatim.
- `TARGET=all` broadcasts.

```bash
command ask "$TARGET" <<'EOF'
$MESSAGE
EOF
```

After submit, return the command output and stop.
