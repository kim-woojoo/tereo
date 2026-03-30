# PR / CI

The smallest useful PR integration is one sticky receipt comment.

<p>
  <img
    src="https://raw.githubusercontent.com/kim-woojoo/tereo/main/assets/readme/tereo-pr-comment-preview.svg"
    alt="TEREO sticky PR comment preview"
    width="860"
  />
</p>

Copy:

- `runtime/examples/github/tereo-pr-comment.yml` -> `.github/workflows/tereo-pr-comment.yml`
- `runtime/examples/github/tereo-pr-comment.sh` -> `.github/scripts/tereo-pr-comment.sh`

That example workflow does five things:

1. checks out the base branch
2. records one baseline
3. checks out the PR head
4. proves one small change
5. updates the same PR comment

It starts without `control`.
Add `tereo control --repeat 5` only when the check is noisy or metric-based.

The sticky update comes from:

```bash
tereo comment | bash .github/scripts/tereo-pr-comment.sh
```

It intentionally starts with trusted same-repo PRs.
That keeps the first integration small and safe.

Example PR comment:

```md
## TEREO

`KEEP` · `HIGH`

`tests: 41 -> 42 passing (+1)`
Parser handles empty input
baseline: `tests: 42 passing`
net: `tests: 41 -> 42 passing; +1`

> keep only if gain > noise
```

The habit is not only "tests passed."
It is:

- what changed
- what check stayed fixed
- what got better
- how strong the evidence was
