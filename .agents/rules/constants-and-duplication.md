# Named constants and mandatory extraction of duplicated code

Applies to all project code, including application code, tests, scripts and tooling.
These requirements are mandatory during implementation, maintenance and review.

## Define literals as constants

**Operational literals (magic strings and numbers) must be named constants and
referenced by name.** This is not a ban on every string or numeric literal.
Docstrings, comments and human-readable prose may remain inline.

Define constants for values that encode behavior or a shared contract, including:

- Timeouts, delays, polling intervals, retry counts, limits, sizes and thresholds.
- File and directory names, path components, extensions, globs and regular expressions.
- JSON/object keys, configuration keys, environment variable names and protocol fields.
- Command names, CLI flags, status values, error codes and configurable defaults.

For example, `json_obj["my_key"]` must use a named key constant; a function's
literal docstring is fine. Test and script code follows the same distinction:
operational keys, paths and timing values require constants, while explanatory
text and sample payload prose do not. Declarative configuration and manifests
use their native literal syntax; do not generate indirection solely to avoid it.

Use descriptive names that communicate meaning and, where relevant, units, such as
`SERVICE_STARTUP_TIMEOUT_SECONDS`, `MAX_RETRY_ATTEMPTS` or `JSON_KEY_STATUS`.
Follow the language's constant or enum conventions. An ordinary mutable variable
is not a substitute for a constant.

Define each semantic constant once in the appropriate module, class or shared
constants module; import or reference it at every use. Do not duplicate its
definition across functions or files. Equal values with different meanings may
have different constants; do not couple unrelated behavior merely because the
current values happen to match.

Runtime configuration may override a named default constant. Values obtained at
runtime must remain dynamic; this rule does not authorize replacing them with
hardcoded values.

A short or single-use operational literal still requires a constant. Ordinary
language syntax, such as a main-module guard, and structural values such as an
empty string, a zero-based index or a counter increment are not magic values.
For generated artifacts, fix their authoritative source or generator instead of
hand-editing generated output.

## Extract duplicated code

Within a project, extract a repeated block into a shared method or function when
either threshold is met:

| Block length | Total occurrences requiring extraction |
| --- | --- |
| 5 or more code lines | 3 or more occurrences: the original plus at least 2 copies |
| 8 or more code lines | 2 or more occurrences: the original plus at least 1 copy |

The thresholds are inclusive and apply independently. An 8-line block repeated
twice must be extracted even though it has fewer than 3 total occurrences.

Count nonblank, non-comment code lines using the project's normal formatting.
Compare blocks across the entire project, including different files, classes,
commands and tests. Blocks with the same logic still count when their only
differences are variable names or values that can be passed as parameters.

Extract the common behavior once, pass varying inputs as parameters, and replace
every qualifying copy with a call to that method or function. Choose a meaningful
name and a location accessible to its callers. Merely moving copies, renaming
variables, altering formatting or replacing literals with constants does not
satisfy the extraction requirement.

Before completing a change, check the code being added or modified for inline
operational literals and qualifying duplication, including matching blocks elsewhere in the
project. Correct violations in that work and validate that extraction preserves
behavior.
