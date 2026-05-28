# Contributing to VIPER

Thank you for contributing!  
This guide helps balance innovation and proof-of-concept work with stability and structure across the team.

VIPER supports multiple Public Health Units (PHUs), so we stress reproducibility, clarity, and intent within our coding practices and documentation. 

## Learning Culture 

VIPER is a space for learning, curiosity, and shared growth.
We build together; experimenting thoughtfully, documenting clearly, and helping one another improve. Mistakes, proof-of-concepts, and even unfinished ideas are part of how we learn and strengthen our systems.

Every contribution, whether it’s a small fix, a new feature, or an exploratory idea, helps us refine both the codebase and our collective understanding. We value kindness, openness, and a spirit of mentorship in every review, discussion, and pull request.

---

## 1. Goals
- Encourage new ideas while maintaining production readiness.
- Ensure transparency in design and review processes.
- Support collaboration and learning in a growing dev team.
- Promote *responsible AI use*; we use AI as a partner in coding, but not a replacement for understanding.

---

## 2. Branching and Feature Work

| Type | Branch Prefix | Description | Merge Timing |
|------|----------------|--------------|---------------|
| Bug fix | `fix/` | Patches or small improvements | Anytime |
| Docs | `docs/` | Improvements to documentation without changes to functionality | Anytime |
| Enhancement | `feat/` | New features or updates | Before code freeze |
| Proof of Concept | `poc/` | Exploratory or experimental work | Not merged until reviewed |
| Refactor | `refactor/` | Structural reorganization | Requires discussion before starting |

**Branching Principles**
* Keep branches small and purposeful; one concept per PR
* Large or multi-feature PRs are discouraged; split them by concern
* Tag experimental branches clearly (`poc/ai-generated-utility`, `poc/new-typst-flow`)

---

## 3. Process for Major Changes
1. **Open an Issue** before starting a large refactor or new feature.
2. **Discuss scope and timing** with the lead dev or tech manager (especially before ISPA season).
3. **Link commits** to issues (e.g., `Closes #12`).
4. **Request a review** before merging into `main`.
5. **Describe rationale** for improvements, including motivation and context, expected impact, testing and validation plan. Include your thoughts about scalability, reproducibility, and replicability while considering the needs of our PHU and other PHUs across Ontario.

---

## 4. Code Standards
- **Python:**
    * Include docstrings and type hints on all new functions and classes
    * Maintain consistent logging and clear variable naming
    * Keep functions modular; small, testable, single purpose 
- **Typst:** 
    * Data and layout remain decoupled. Python produces structured data; Typst handles rendering
    * Test template changes with mock data before PR
- **Commit messages:** Be descriptive and reference issues.

---

## 5. Production Freeze
During ISPA production season:
- No major refactors or architectural changes.
- Only bug fixes, configuration updates, and content changes are allowed.

---

## 6. Review Principles
- Focus on readability, maintainability, and alignment with existing design.
- Keep discussions respectful; we learn by explaining our reasoning.
- Proof-of-concept work is encouraged but should be scoped and documented.
- Both AI and human-generated code must be understood by the contributor
- Try to treat reviews as knowledge sharing (this is fun!): explain why something works :)

---

## 7. Documentation and Testing 
* Update or create new documentation if your change alters workflows, configs, or outputs 
* Add or update unit tests and mock data
* Run Typst compile smoke tests on sample data before merging 

---

## 8. Acknowledging Efforts 

Value team efforts, ideas, experimentation, and initiative. 

Even if not merged, branches contribute to team learning and future iteration! 

---

## 9. Questions and Collaboration

For guidance or clarification: 

* Tag our team in PR or issue
* Use our GitHub or Teams for conceptual proposals 

## Closing Thought

VIPER thrives on collaboration, curiosity, and accountability.
By contributing, you help build not only reliable software but a culture of learning and shared ownership.

