# cc-1c-skills attribution

The structural-validation layer in this repository is informed by the MIT-licensed project:

`Nikolay-Shirokov/cc-1c-skills` — https://github.com/Nikolay-Shirokov/cc-1c-skills

For the bounded OneCChatWorker Q0 local quality adapter, exactly three upstream scripts are redistributed unchanged from commit
`1fa205b961f4ed3659f58f4b55d2d9b1d5e4810e`:

- `.claude/skills/meta-info/scripts/meta-info.ps1` — git blob `cf1a233e7fb270325a91dd8403ca96794d26c7d9`
- `.claude/skills/form-info/scripts/form-info.ps1` — git blob `0edda69123ce565938bf368ff26039a890ac23d1`
- `.claude/skills/form-validate/scripts/form-validate.ps1` — git blob `208e9ee4c543c7ef85ead5465f1abf5ecff19a3f`

They are installed only behind the internal allowlisted adapter. No upstream repository, skill router, generic execution surface, daemon, or rule registry is adopted.

The local `TOOLS/analyze_onec_xml.py` remains an independent smaller integration under the existing evidence/release architecture. The Q0 adapter does not replace its ownership.

See `LICENSE.txt` for the upstream MIT license.
