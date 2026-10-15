# Template Customization Options

Notice wording and display options are authored in the Template and Settings.
The images below illustrate customization choices from an earlier pilot; use the
[current template guide](../phu_templates.md) for the maintained options and files.

## Pages

The maintained disease and agent examples have two sections, usually one page each:


1. Client Information and Messaging
2. Immunization History Chart

Long content may continue onto additional pages. The PDF remains available with
layout findings for review; content is not clipped or reduced to fit.

## Client Information and Messaging Page

The Client Information and Messaging page consists of 5 customizable components: 

![Client Information and Messaging page](images/20251027_page1.jpeg)

### 1. Header

The header consists of: 

* a `.png`, `.svg` or `.jpeg` file of your Public Health Units logo 
* messaging requesting immunization record. This messaging can be customized but **should not span more than 2 lines**

### 2. Client Information Table

#### Formatting 

Settings places client details beside or below the address. The older pilot
images illustrate alternative table arrangements an author may create in Typst: 

**Equal columns (50/50 split) with vertical line:**

![Client Information Table with 50/50 split and a vertical line](images/20251027_5050_vline.jpeg)

**Unequal columns (40/60 split) with vertical line:**

![Client Information Table with 40/60 split and a vertical line](images/20251027_4060_vline.jpeg)

**Equal columns (50/50 split) without vertical line:**

![Client Information Table with 50/50 split and no vertical line](images/20251027_5050_no_vline.jpeg)

**Unequal columns (40/60 split) without vertical line:**

![Client Information Table with 40/60 split and no vertical line](images/20251027_4060_no_vline.jpeg)

#### Dynamic Content 

The content within the box contains the following information about the child: 

* Name
* Address
* City 
* Province
* Postal Code
* Ontario Immunization ID or Client ID 
* Date of Birth
* Childcare Centre or School

The addressee follows the known age supplied in the facts. When age is unknown,
the maintained examples use neutral wording and report the missing information.

### 3. Immunization List

The immunization list is an optional component. It lists all outstanding immunizations for the client. 

Settings controls list columns and whether dose numbers are shown. Long lists
remain visible, with a finding if the notice continues onto another page.

The messaging prior to the immunization list can be customized according to your preference. We recommend keeping a data in the message to ensure that the client is aware of when the immunization data was pulled from the system.

### 4. Messaging

The messaging is fully customizable based on the Public Health Unit's needs.

### 5. Signature

The signature consists of 3 components: 

1. A `.png`, `.svg`, `.jpeg` file of the signature (in the diagram we use a logo as a placeholder for the signature)
2. The name of the sender
3. The title of the sender 

## Immunization History Chart

The immunization history chart starts the history section when the template
includes it. Omitting history, as the suspension example does, creates no
history checks.

![Immunization History Chart](images/20251027_page2.jpeg)

There are 2 main components on the immunization history page (marked as 6 and 7 on the
image above):

6. Header
7. Immunization History Chart

### 6. Header 

The header consists of: 

* `.png`, `.svg`, or `.jpeg` file of your PHUs logo
* Title of page: "Immunization Record

### 7. Immunization History Table

There are several components of the immunization table. We have further broken down the components in the image below: 

(a) Names of diseases

These can be customized. In some cases, other may be replaced with HPV , for instance,
depending on the age of the use case for the reports.

(b) Minimum number of rows in table

Here, if the number of rows is less than 5, we pad the table with blank rows for aesthetic
purposes. The minimum number of rows can be adjusted based on preference.

(c) You may also wish to customize the chart to include an additional column "At Age"

![Immunization History Chart](images/20251027_immunization_history.jpeg)
![Immunization History Chart](images/20251027_immunization_history_age.jpeg)


