# CONTEXT_HANDOFF_RULES.md

Version: 2.0
Status: Stable

---

# 1. Purpose

This document defines the rules for handing off project context between AI conversations.

Its only purpose is to ensure that a new AI session can continue development with:

- correct project understanding
- minimal context consumption
- no loss of important information

This document does NOT define project architecture, coding standards, or development workflow.

Those belong to other project documents.

---

# 2. When to Generate a New Conversation Prompt

Generate a New Conversation Prompt (NCP) whenever one of the following occurs:

- the current conversation is approaching the context limit
- switching to another AI model
- switching to another AI development tool
- resuming development after a long interruption
- handing the project to another developer or AI

If none of the above applies, do not generate an NCP.

---

# 3. Core Principles

## P1. Repository First

The repository is the single source of truth.

Never duplicate repository documentation inside the prompt.

Always reference project documents instead.

---

## P2. Prompt Is Navigation

A prompt tells the next AI where to read.

It is NOT a project summary.

---

## P3. Keep It Minimal

Only include information that is required to continue the current work.

Everything else should be referenced.

---

## P4. Prefer References

GOOD

Read:

.ai/PROJECT_STATUS.md

BAD

Copy the entire PROJECT_STATUS into the prompt.

---

## P5. Current Session Only

The prompt represents the current session.

It must never become permanent documentation.

---

# 4. Runtime Context

The following files are the project's Runtime Context.

- .ai/AI_ONBOARDING.md
- .ai/PROJECT_STATUS.md
- .ai/ARCHITECTURE_DECISIONS.md
- .ai/KNOWN_ISSUES.md

These files already contain the project knowledge.

The prompt should reference them instead of repeating their contents.

---

# 5. Required Prompt Content

Every New Conversation Prompt should contain only the following information.

## Project

Project name.

Example:

PhotoArchiver

---

## Current Development Step

Current roadmap step.

Example:

Step 11

---

## Current Task

Describe only the task currently being developed.

Do not include completed work.

---

## Current Blockers

List unresolved blockers only.

Do not include resolved issues.

---

## Recent Decisions

Only list new architecture decisions made during the current session.

Use one-line summaries.

Example:

ADR-012

ArchiveService uses independent archive_root configuration.

---

## Required Reading

List the Runtime Context documents that must be read.

Do not summarize them.

Example:

Read:

.ai/AI_ONBOARDING.md

.ai/PROJECT_STATUS.md

.ai/ARCHITECTURE_DECISIONS.md

.ai/KNOWN_ISSUES.md

---

# 6. Loading Order

Every generated prompt should instruct the next AI to load project information in the following order.

1. AI_ONBOARDING.md

2. PROJECT_STATUS.md

3. ARCHITECTURE_DECISIONS.md

4. KNOWN_ISSUES.md

5. Documents related to the current task

6. Relevant source code

Do not read unrelated files.

---

# 7. Stop Loading Rule

After loading the Runtime Context, stop.

Read additional documents only when required by the current task.

Do not scan the entire repository.

---

# 8. Token Optimization

Whenever possible:

- reference instead of explain
- use document paths instead of summaries
- use ADR IDs instead of architecture descriptions
- include only current information
- remove obsolete information

Target prompt size:

Ideal:

<700 tokens

Recommended:

<1000 tokens

Maximum:

<1500 tokens

---

# 9. Session Close Output

Before ending the current conversation, prepare a handoff summary.

The summary should include:

Current Step

Current Task

Current Blockers

Recent ADRs

Runtime Context updated

Next recommended task

Ready for next session

Nothing else.

---

# 10. Prompt Checklist

Before generating the prompt, verify:

✓ Current task is clear

✓ Current roadmap step is correct

✓ Current blockers are listed

✓ New ADRs are listed

✓ Runtime Context files are referenced

✓ No duplicated documentation exists

✓ Prompt stays within token budget

✓ Prompt only contains current session information

---

# 11. Forbidden Content

Never include:

- README contents
- AI_ONBOARDING contents
- architecture documents
- coding standards
- dependency rules
- roadmap details
- historical discussions
- entire markdown files
- long code snippets
- completed tasks
- resolved issues

Reference them instead.

---

# 12. Guiding Philosophy

The repository stores knowledge.

The Runtime Context stores project state.

The prompt only transfers navigation.

A good handoff prompt is:

- short
- accurate
- up to date
- easy to load
- easy to discard

After the next AI session begins, the prompt has completed its purpose.
