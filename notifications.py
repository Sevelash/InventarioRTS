"""
RTS Notification Engine
Channels: Microsoft Teams (Incoming Webhook) + Email (SMTP / Office 365)
Config  : instance/notify_config.json  (not tracked by git)
"""
import json, os, threading, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'notify_config.json')

DEFAULT_CONFIG = {
    "enabled":                   False,
    # Teams
    "teams_enabled":             True,
    "teams_webhook_url":         "",
    "teams_channel_name":        "RTS Projects",
    # Email
    "email_enabled":             False,
    "smtp_host":                 "smtp.office365.com",
    "smtp_port":                 587,
    "smtp_user":                 "",
    "smtp_password":             "",
    "smtp_from":                 "",
    "smtp_from_name":            "RTS Intranet",
    # App
    "app_base_url":              "http://localhost:5050",
    # Event toggles
    "notify_task_assigned":      True,
    "notify_status_change":      True,
    "notify_comment":            True,
    "notify_project_created":    True,
    "notify_project_updated":    True,
}


def load_config() -> dict:
    try:
        with open(_CONFIG_PATH, 'r') as f:
            data = json.load(f)
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(data)
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_config(data: dict) -> dict:
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    cfg = dict(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
    with open(_CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)
    return cfg


# ── Microsoft Teams ───────────────────────────────────────────────────────────

def _teams_post(webhook_url: str, payload: dict):
    try:
        import urllib.request
        body = json.dumps(payload).encode('utf-8')
        req  = urllib.request.Request(
            webhook_url, data=body,
            headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f'[RTS/Teams] {e}')


def send_teams(title: str, text: str,
               facts: list[tuple] | None = None,
               url:   str | None = None,
               color: str = '0076D7'):
    """Send an Office 365 MessageCard to Teams. Fire-and-forget (background thread)."""
    cfg = load_config()
    if not cfg.get('enabled') or not cfg.get('teams_enabled') or not cfg.get('teams_webhook_url'):
        return

    section = {
        'activityTitle':    f'**{title}**',
        'activitySubtitle': cfg.get('teams_channel_name', 'RTS Intranet'),
        'activityText':     text,
    }
    if facts:
        section['facts'] = [{'name': k, 'value': str(v)} for k, v in facts]

    card = {
        '@type':      'MessageCard',
        '@context':   'https://schema.org/extensions',
        'themeColor': color,
        'summary':    title,
        'sections':   [section],
    }
    if url:
        card['potentialAction'] = [{
            '@type': 'OpenUri', 'name': 'Open in RTS',
            'targets': [{'os': 'default', 'uri': url}],
        }]

    threading.Thread(
        target=_teams_post,
        args=(cfg['teams_webhook_url'], card),
        daemon=True
    ).start()


# ── Email (SMTP / Office 365) ─────────────────────────────────────────────────

_EMAIL_HTML = """\
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  body{{font-family:'Segoe UI',Calibri,Arial,sans-serif;margin:0;padding:0;background:#F4F6F9;}}
  .wrap{{max-width:600px;margin:30px auto;background:#fff;border-radius:12px;
         overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.09);}}
  .hdr{{background:#233C6E;padding:24px 28px;}}
  .hdr-t{{color:#fff;font-size:22px;font-weight:700;margin:0;letter-spacing:.02em;}}
  .hdr-s{{color:rgba(255,255,255,.55);font-size:12px;margin:4px 0 0;}}
  .bdy{{padding:28px 30px;}}
  .ttl{{font-size:17px;color:#233C6E;font-weight:700;margin:0 0 10px;}}
  .txt{{font-size:14px;color:#54595F;line-height:1.65;margin:0 0 18px;}}
  table.facts{{width:100%;border-collapse:collapse;margin:14px 0;}}
  table.facts td{{padding:8px 10px;font-size:13px;border-bottom:1px solid #EEF1F6;}}
  table.facts td:first-child{{color:#7A7A7A;font-weight:600;width:36%;}}
  table.facts td:last-child{{color:#233C6E;font-weight:500;}}
  .cta{{display:inline-block;background:#089ACF;color:#fff;text-decoration:none;
        padding:11px 24px;border-radius:8px;font-size:14px;font-weight:700;margin-top:10px;}}
  .ftr{{background:#F8F8F8;padding:14px 28px;font-size:11px;color:#bbb;
        border-top:1px solid #EEF1F6;text-align:center;line-height:1.6;}}
</style></head><body>
<div class="wrap">
  <div class="hdr">
    <div class="hdr-t">Remote Team Solutions</div>
    <div class="hdr-s">RTS Intranet · Automated Notification</div>
  </div>
  <div class="bdy">
    <div class="ttl">{title}</div>
    <div class="txt">{text}</div>
    {facts_html}
    {cta_html}
  </div>
  <div class="ftr">
    &copy; 2026 Remote Team Solutions &nbsp;&middot;&nbsp;
    This is an automated message. Please do not reply directly to this email.
  </div>
</div>
</body></html>"""


def _build_html(title: str, text: str,
                facts: list[tuple] | None = None,
                url:   str | None = None) -> str:
    rows = ''.join(
        f'<tr><td>{k}</td><td>{v}</td></tr>' for k, v in (facts or [])
    )
    facts_html = f'<table class="facts">{rows}</table>' if rows else ''
    cta_html   = f'<a href="{url}" class="cta">Open in RTS ↗</a>' if url else ''
    return _EMAIL_HTML.format(
        title=title, text=text,
        facts_html=facts_html, cta_html=cta_html)


def _smtp_send(cfg: dict, to_list: list[str], subject: str, html: str):
    from_addr = cfg.get('smtp_from', '')
    from_name = cfg.get('smtp_from_name', 'RTS Intranet')
    try:
        with smtplib.SMTP(cfg['smtp_host'], int(cfg['smtp_port'])) as srv:
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
            srv.login(cfg['smtp_user'], cfg['smtp_password'])
            for to in to_list:
                if not to or '@' not in str(to):
                    continue
                msg           = MIMEMultipart('alternative')
                msg['Subject']= subject
                msg['From']   = f'{from_name} <{from_addr}>'
                msg['To']     = to
                msg.attach(MIMEText(html, 'html', 'utf-8'))
                srv.sendmail(from_addr, to, msg.as_string())
    except Exception as e:
        print(f'[RTS/Email] {e}')


def send_email(to_emails, subject: str, title: str, text: str,
               facts: list[tuple] | None = None,
               url:   str | None = None):
    """Send branded HTML email. Fire-and-forget."""
    cfg = load_config()
    if not cfg.get('enabled') or not cfg.get('email_enabled') or not cfg.get('smtp_user'):
        return
    if isinstance(to_emails, str):
        to_emails = [to_emails]
    to_emails = [e for e in to_emails if e and '@' in str(e)]
    if not to_emails:
        return
    html = _build_html(title, text, facts, url)
    threading.Thread(
        target=_smtp_send,
        args=(cfg, to_emails, subject, html),
        daemon=True
    ).start()


# ── High-level event helpers ──────────────────────────────────────────────────

def _url(cfg: dict, path: str) -> str:
    return cfg.get('app_base_url', '').rstrip('/') + path


def on_task_assigned(task, project, assignee, by_name: str):
    cfg = load_config()
    if not cfg.get('enabled') or not cfg.get('notify_task_assigned'):
        return
    url   = _url(cfg, f'/projects/{project.id}')
    title = f'Task assigned: {task.title}'
    text  = f'{by_name} assigned you a task in project **{project.name}**.'
    facts = [
        ('Project',  project.name),
        ('Task',     task.title),
        ('Priority', task.priority.capitalize()),
        ('Due date', str(task.due_date) if task.due_date else 'Not set'),
    ]
    send_teams(title, text, facts=facts, url=url, color='0076D7')
    if assignee and assignee.email:
        send_email(assignee.email,
                   f'[RTS] Task assigned to you: {task.title}',
                   title, f'{by_name} assigned you a new task in <b>{project.name}</b>.',
                   facts=facts, url=url)


def on_task_status_changed(task, project, old_st: str, new_st: str, by_name: str):
    cfg = load_config()
    if not cfg.get('enabled') or not cfg.get('notify_status_change'):
        return
    labels = {'pending': 'To Do', 'in_progress': 'In Progress',
              'review': 'In Review', 'done': 'Done', 'cancelled': 'Cancelled'}
    colors = {'done': '28A745', 'cancelled': 'DC3545',
              'in_progress': '0076D7', 'review': 'FFA000'}
    url   = _url(cfg, f'/projects/{project.id}')
    title = f'Task updated: {task.title}'
    text  = (f'{by_name} moved **{task.title}** from '
             f'_{labels.get(old_st, old_st)}_ → **{labels.get(new_st, new_st)}** '
             f'in {project.name}.')
    send_teams(title, text, url=url, color=colors.get(new_st, '233C6E'))
    if task.assigned_to and task.assigned_to.email:
        send_email(task.assigned_to.email,
                   f'[RTS] Task status updated: {task.title}',
                   title,
                   f'{by_name} updated your task in <b>{project.name}</b>.',
                   facts=[('New status', labels.get(new_st, new_st))], url=url)


def on_comment_added(comment_text: str, task, project, by_name: str):
    cfg = load_config()
    if not cfg.get('enabled') or not cfg.get('notify_comment'):
        return
    url   = _url(cfg, f'/projects/{project.id}')
    title = f'New comment on: {task.title}'
    text  = f'{by_name} commented on task **{task.title}** in {project.name}.'
    send_teams(title, text,
               facts=[('Comment', comment_text[:200])],
               url=url, color='6264A7')
    if task.assigned_to and task.assigned_to.email:
        send_email(task.assigned_to.email,
                   f'[RTS] New comment: {task.title}',
                   title,
                   f'{by_name} left a comment on your task <b>{task.title}</b>.',
                   facts=[('Comment', comment_text[:200])], url=url)


def on_project_created(project, by_name: str):
    cfg = load_config()
    if not cfg.get('enabled') or not cfg.get('notify_project_created'):
        return
    url   = _url(cfg, f'/projects/{project.id}')
    title = f'New project: {project.name}'
    text  = f'{by_name} created project **{project.name}** ({project.code}).'
    facts = [
        ('Code',     project.code),
        ('Priority', project.priority.capitalize()),
        ('Status',   project.status.capitalize()),
    ]
    if project.end_date:
        facts.append(('Due date', str(project.end_date)))
    send_teams(title, text, facts=facts, url=url, color='233C6E')


def on_project_status_changed(project, old_st: str, new_st: str, by_name: str):
    cfg = load_config()
    if not cfg.get('enabled') or not cfg.get('notify_project_updated'):
        return
    labels = {'planning': 'Planning', 'active': 'Active', 'on_hold': 'On Hold',
              'completed': 'Completed', 'cancelled': 'Cancelled'}
    colors = {'completed': '28A745', 'cancelled': 'DC3545', 'active': '0076D7'}
    url    = _url(cfg, f'/projects/{project.id}')
    title  = f'Project updated: {project.name}'
    text   = (f'{by_name} changed **{project.name}** from '
              f'_{labels.get(old_st, old_st)}_ → **{labels.get(new_st, new_st)}**.')
    send_teams(title, text, url=url, color=colors.get(new_st, '233C6E'))
