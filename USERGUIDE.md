# CloudSpyglass User Guide

CloudSpyglass is an AWS infrastructure visualization tool that scans your AWS account, discovers resources and their relationships, and renders an interactive architecture diagram in your browser.

---

## Table of Contents

1. [The Diagram Panel](#1-the-diagram-panel)
2. [Changing the Language](#2-changing-the-language)
3. [Setting Up AWS Credentials](#3-setting-up-aws-credentials)
4. [Auto-Refresh](#4-auto-refresh)
5. [Configuring A.I. API Credentials](#5-configuring-ai-api-credentials)
6. [Selecting Regions](#6-selecting-regions)
7. [Scanning and Viewing Your Architecture](#7-scanning-and-viewing-your-architecture)
8. [Filtering Resources](#8-filtering-resources)
9. [AI Architecture Advisor](#9-ai-architecture-advisor)
10. [Exporting Your Diagram](#10-exporting-your-diagram)

---

## 1. The Diagram Panel

When you first open CloudSpyglass, you land on the **Diagram** panel. This is the main workspace where your architecture diagrams will be displayed.

Initially, the canvas is empty and shows the message: *"No scan data available. Click 'Scan' above to discover your AWS infrastructure."*

The top navigation bar contains:
- **Language selector** (top-right globe icon)
- **Diagram** / **Settings** tabs to switch between views
- **Region selector** dropdown to choose which AWS regions to scan
- **Scan** button to start discovering your infrastructure

![Diagram Panel](assets/screencaptures/diagram_panel.png)

---

## 2. Changing the Language

CloudSpyglass supports multiple languages. Click the **language dropdown** (globe icon with "EN") in the top-right corner to switch between:

- English
- Español
- Português

The entire interface will update to reflect your language choice.

![Language Selector](assets/screencaptures/diagram_panel_language_dropbox.png)

---

## 3. Setting Up AWS Credentials

Before scanning, you need to connect your AWS account. Navigate to the **Settings** tab to configure your credentials.

### Connecting Your Account

In the **AWS Credentials** section, fill in:

1. **Access Key ID** — your AWS access key
2. **Secret Access Key** — your AWS secret key
3. **Session Token** (optional) — required if you're using temporary credentials (e.g., from AWS STS)

Click the **Connect** button to authenticate. The **Credential Status** card at the top will show the current connection state.

![Credentials Section](assets/screencaptures/settings_panel_credentials_section.png)

### Successful Connection

Once connected, the status changes to **Connected** (green indicator) and displays:
- **Account ID** — the AWS account number
- **Source** — how the credentials were provided (e.g., "UI-provided")
- **Expiry** — credential expiration info

You can click **Disconnect** at any time to remove the stored credentials.

![Credentials Connected](assets/screencaptures/settings_panel_credentials_connected.png)

---

## 4. Auto-Refresh

Below the credentials section in **Settings**, you'll find the **Auto-Refresh Interval** setting. This controls how often CloudSpyglass automatically re-scans your AWS account to detect infrastructure changes.

Available intervals:
- **Manual** (default) — no automatic rescanning; you trigger scans manually
- **1 minute**
- **5 minutes**
- **15 minutes**
- **30 minutes**
- **60 minutes**

Select the interval that fits your workflow. For actively changing environments, shorter intervals keep your diagram current. For stable infrastructure, manual mode avoids unnecessary API calls.

![Auto-Refresh Settings](assets/screencaptures/settings_panel_autorefresh.png)

---

## 5. Configuring A.I. API Credentials

To use the **AI Architecture Advisor** feature, you need to configure your A.I. API credentials in the **Settings** panel.

The **A.I. API Credentials** section is located below the Auto-Refresh settings. Click the **"Define your own A.I. API credentials"** button to expand the configuration form. Fill in the following fields:

1. **Base URL** — the API endpoint URL (e.g., `https://api.groq.com/openai/v1`)
2. **Model** — the model identifier to use (e.g., `openai/gpt-oss-120b`)
3. **API Key** — your API key for authentication

CloudSpyglass is compatible with the **OpenAI API standard**. This means you can use any provider that implements this standard, such as **Groq**, **OpenRouter**, **Gemini**, **Together AI**, or your own self-hosted models. Simply provide the appropriate Base URL, model name, and API key for your chosen provider.

Once you've entered your credentials, click **"Validate & Save"**. The application will attempt to reach the API and verify your credentials.

![Custom AI API Credentials](assets/screencaptures/settings_panel_custom_ai_api_credentials.png)

### Successful A.I. Connection

If validation succeeds, the section displays:
- **Connected** status (green indicator)
- **Model** — the configured model name
- **Validated** — date and time of the last successful validation

You can click **"Reset to defaults"** to clear your custom credentials and revert to the default configuration.

![AI API Credentials Connected](assets/screencaptures/settings_panel_ai_api_credentials_connected.png)

---

## 6. Selecting Regions

Before scanning, you can limit the discovery to specific AWS regions. Click the **region dropdown** (shows "All Regions" by default) next to the Scan button.

A checklist appears with all available AWS regions. Select one or more regions to narrow the scan scope. The dropdown label updates to show how many regions are selected (e.g., "1 region").

Use **Clear all** to deselect everything, or leave all unchecked to scan all regions.

Limiting regions speeds up the scan and focuses the diagram on the infrastructure you care about.

![Region Selector](assets/screencaptures/diagram_panel_regions_dropbox.png)

---

## 7. Scanning and Viewing Your Architecture

### Starting a Scan

Click the **Scan** button to begin discovering resources. During the scan:
- The button changes to **"Scanning..."** with a loading spinner
- A timer shows elapsed time
- A **Stop** button appears if you need to cancel

![Scanning Process](assets/screencaptures/diagram_panel_scanning_process.png)

### Viewing the Architecture Diagram

Once the scan completes, your AWS infrastructure is rendered as an interactive diagram. Resources are organized hierarchically:
- **AWS Cloud** → **Account** → **Region** → **Availability Zone** → **VPC** → **Subnet** → individual resources

The diagram is fully interactive — you can **pan** (click and drag the canvas), **zoom** (scroll wheel), and use the **Fit View** button to auto-fit the entire diagram in the viewport. Zoom controls (+/-) are available in the bottom-left corner.

![Architecture Diagram](assets/screencaptures/diagram_panel_example_architecture.png)

### Inspecting Resources

Click on any resource node in the diagram to open a **detail panel** on the right side. This panel shows:
- **Identifiers** — ARN and resource ID
- **Region** — where the resource is located
- **Name** — the resource name
- **Tags** — all AWS tags attached to the resource
- **Creation Date** — when the resource was created
- **Attributes** — service-specific details (e.g., engine type and version for ElastiCache)

Close the panel by clicking the **X** button.

![Inspecting Resources](assets/screencaptures/diagram_panel_inspecting_resources.png)

---

## 8. Filtering Resources

After a scan, CloudSpyglass provides two filtering mechanisms to focus on what matters. The filter panels are collapsible — click the triangle icon to expand or collapse them.

### Resource Type Filter

The **Resource Types** section displays all discovered service types as clickable chips (e.g., `ec2`, `s3`, `lambda`, `rds`). Click a specific type to show only resources of that kind. The counter updates to reflect how many resources are visible (e.g., "4 of 399 resources").

Use **All** to show everything or **None** to hide all, then selectively enable types. A **Clear All** link resets all filters.

![Service Filter](assets/screencaptures/diagram_panel_example_service_filter.png)

### Tag Filters

The **Tag Filters** section lets you filter resources by their AWS tags. Enter a **Key** and **Value**, then click **Add** to apply the filter. Only resources matching all specified tag key-value pairs will be shown (AND logic).

This is useful for isolating resources by environment (e.g., `Environment: production`), team, project, or any custom tagging strategy you use.

![Tag Filters](assets/screencaptures/diagram_panel_tag_filters.png)

---

## 9. AI Architecture Advisor

The **AI Architecture Advisor** is an intelligent analysis tool that reviews your scanned infrastructure and provides actionable recommendations. Navigate to the **Advisor** tab in the top navigation bar.

### Analysis Pillars

The Advisor lets you choose which aspects of your architecture to analyze. Select one or more **Analysis Pillars**:

- **Security** — identifies potential security risks, overly permissive roles, and access control issues
- **Cost Optimization** — suggests ways to reduce unnecessary spending (e.g., missing S3 lifecycle policies, over-provisioned resources)
- **Performance** — highlights bottlenecks and optimization opportunities

Check the pillars you're interested in, then click **"Analyze Architecture"**. The AI will evaluate your scanned resources and return findings grouped by pillar, each with a severity level (HIGH, MEDIUM, etc.), a description of the issue, the affected resources (listed by ARN), and the estimated impact.

![AI Advisor - Cost Optimization Analysis](assets/screencaptures/advisor_panel_raw_cost_optimization_example.png)

### Filters Are Reflected in the Advisor

If you have active filters on the **Diagram** page (resource type filters or tag filters), the Advisor will analyze only the filtered subset of resources. A green banner confirms this: *"Analysis will use filters from Diagram page (X type filter, Y tag filters)"*.

This allows you to focus the AI analysis on specific parts of your infrastructure — for example, analyzing only IAM resources for security, or only EC2 instances for performance.

![AI Advisor - Filtered Analysis](assets/screencaptures/advisor_panel_filtered_security_optimization.png)

---

## 10. Exporting Your Diagram

Once you have your diagram configured and filtered to your liking, click the **Export** button (top-right, purple) to download it. Three formats are available:

- **PDF** — multi-page document, ideal for sharing and printing
- **PNG (300 DPI)** — high-resolution image, great for presentations and documentation
- **SVG** — scalable vector format, perfect for embedding in web pages or further editing

![Export Options](assets/screencaptures/diagram_panel_export_dropbox.png)
