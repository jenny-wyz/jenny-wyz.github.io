---
title: "{{ replace .Name "-" " " | title }}"
date: {{ .Date }}
draft: true
summary: ""
tags: []
categories: ["{{ path.Base (path.Dir .File.Dir) }}"]
---

