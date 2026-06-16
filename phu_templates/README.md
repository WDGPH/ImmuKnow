# WDGPH VIPER Template Library

The VIPER Template Library is a private repository that provides a centralized, version-controlled collection of reusable templates that are used across provinical Public Health VIPER workflows. 

This includes Typst document templates, YAML configuration schemas, and other standardized assets reuqired by the VIPER pipeline.

By storing these artifacts in a dedicated private repostiroy and consuming them as a Git submodule, we ensure the following: 

* Reproducibiltiy: downstream pipelines reference an exact, pinned version
* Consistency: all PHUs use the same reviewed and approved templates
* Governance: updates are traceable, reviewable, and versioned
* Modularity: templates remain independent from pipeline logic
* Security: PHU-specific assets remain internal and controlled

This repository is intended for **internal** use and is included as a **submodule** inside downstream pipelienes under: 

```
/pipeline/phu_templates
```

Pipeline developers are encouraged to update the submodule when template changes are required, ensuring changes are reviewed and versioned before integration.

## Directory Structure

Templates are stored inside a folder named using the standard PHU acronym. 

Within each PHU folder, templates and assets can follow the following structure: 

```
<PHU_ACRONYM>/
├── assets/
│   ├── logo.png
│   └── signature.png
├──en_template.py
├──fr_template.py
```

## Using the Submodule

Downstream VIPER pipelines consume this repository as a Git submodule, allowing each pipeline to reference a specific, version-controlled snapshot of the templates.

### Adding the Submodule (Initial Setup)

If the pipeline does not yet include the template library:

```
git submodule add <PRIVATE_REPO_URL> phu_templates
git submodule update --init --recursive
```

This will create:

```
phu_templates/   # Points to this template library
```

