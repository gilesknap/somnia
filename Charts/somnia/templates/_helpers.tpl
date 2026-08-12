{{/* Expand the name of the chart. */}}
{{- define "somnia.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified app name, truncated to the 63 characters a DNS label allows.
*/}}
{{- define "somnia.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "somnia.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "somnia.labels" -}}
helm.sh/chart: {{ include "somnia.chart" . }}
{{ include "somnia.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "somnia.selectorLabels" -}}
app.kubernetes.io/name: {{ include "somnia.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Which claim the pods mount: the one named in values, or the one we make. */}}
{{- define "somnia.claimName" -}}
{{- default (include "somnia.fullname" .) .Values.persistence.existingClaim }}
{{- end }}

{{- define "somnia.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) }}
{{- end }}

{{/*
Everything both pods have in common: the same image, the same environment, the
same volume and the same node. Written once because the two must not drift —
they are two halves of one installation sharing one database, and an
environment variable set on one of them only is a bug that shows up hours
later as a book rendered in the wrong voice.

The caller passes the whole context, so this is used as
`include "somnia.podCommon" .` from inside a pod spec.
*/}}
{{- define "somnia.podCommon" -}}
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.podSecurityContext }}
securityContext:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- if .Values.node }}
nodeSelector:
  kubernetes.io/hostname: {{ .Values.node | quote }}
  {{- with .Values.nodeSelector }}
  {{- toYaml . | nindent 2 }}
  {{- end }}
{{- else if .Values.nodeSelector }}
nodeSelector:
  {{- toYaml .Values.nodeSelector | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.affinity }}
affinity:
  {{- toYaml . | nindent 2 }}
{{- end }}
volumes:
  - name: data
  {{- if .Values.persistence.enabled }}
    persistentVolumeClaim:
      claimName: {{ include "somnia.claimName" . }}
  {{- else }}
    emptyDir: {}
  {{- end }}
{{- end }}

{{/* The environment both containers get. See values.yaml `config`. */}}
{{- define "somnia.env" -}}
- name: SOMNIA_DATA_DIR
  value: {{ .Values.dataDir | quote }}
- name: SOMNIA_LIBRARY_DIR
  value: {{ printf "%s/library" .Values.dataDir | quote }}
- name: HF_HOME
  value: {{ printf "%s/huggingface" .Values.dataDir | quote }}
{{- with .Values.config.voice }}
- name: SOMNIA_VOICE
  value: {{ . | quote }}
{{- end }}
{{- with .Values.config.embedModel }}
- name: SOMNIA_EMBED_MODEL
  value: {{ . | quote }}
{{- end }}
{{- with .Values.config.agentModel }}
- name: SOMNIA_AGENT_MODEL
  value: {{ . | quote }}
{{- end }}
{{- with .Values.config.agentEffort }}
- name: SOMNIA_AGENT_EFFORT
  value: {{ . | quote }}
{{- end }}
{{- if .Values.secret.name }}
- name: ANTHROPIC_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secret.name | quote }}
      key: {{ .Values.secret.key | quote }}
{{- end }}
{{- end }}
