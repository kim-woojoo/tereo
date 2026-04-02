# Local Loop

Use TEREO beside your editor or AI pair:

```bash
tereo init --preset pytest
tereo prove --promise "Current tests are green"
# make one small change
tereo prove --scope src/parser.py --promise "Empty input returns []"
tereo show
tereo log
```

The point is simple:
do not trust the patch first.
Trust the receipt.
