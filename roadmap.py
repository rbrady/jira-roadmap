#!/usr/bin/env python
#   Copyright 2020 Ryan Brady<ryan@ryanbrady.org>
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

from collections import Counter
from datetime import datetime
from pprint import pprint

import click
import jinja2
from jira import JIRA


def fetch_issues(connection, jql):
    results = []
    block_size = 100
    block_num = 0
    while True:
        start_idx = block_num * block_size
        issues = connection.search_issues(jql, start_idx, block_size)
        results = results + issues
        if len(issues) == 0:
            # Retrieve issues until there are no more to come
            break
        block_num += 1
    return results


def render_report(template, context):
    with open(template, 'r') as template_file:
        template_data = template_file.read()
        # Render the j2 template
        raw_template = jinja2.Environment(
            extensions=['jinja2.ext.debug']).from_string(template_data)
        pprint(context)
        return raw_template.render(**context, debug=True)


@click.command()
@click.option('--url', default="https://projects.engineering.redhat.com",
              type=str)
@click.option('--project', default=None, type=str)
@click.option('--user', default=None, type=str)
@click.option('--password', default=None, type=str)
@click.option('--template', '-t', default="templates/default_roadmap.j2",
              type=str)
@click.option('--output', default="./generated-roadmap.{0}.html".format(
    datetime.now().timestamp()), type=str)
@click.option('--labels', '-l', multiple=True)
@click.option('--ignores', '-i', multiple=True)
@click.option('--jql', default=None, type=str)
@click.option('--sslverify', default=False, type=bool)
@click.option('--verbose', '-v', is_flag=True)
@click.option('--title', default="Roadmap", type=str)
def roadmap(url, project, user, password, template, output, labels, ignores,
            jql, sslverify, verbose, title):
    # create options from args
    options = {
        "server": url,
        "verify": sslverify,
    }
    auth = (user, password)

    # create connection
    jira = JIRA(auth=auth, options=options)

    if not jql:
        all_issues_jql = f"project={project} and labels={' and labels='.join(labels)}"
    else:
        all_issues_jql = jql

    if verbose:
        print(all_issues_jql)
    all_issues = fetch_issues(jira, all_issues_jql)

    epic_issues = [issue for issue in all_issues if
                   issue.fields.issuetype.name == "Epic"]

    epics = {i.key: {'epic': i, "issues": [], "status": {}} for i in
             epic_issues}
    unassociated = []

    for issue in all_issues:
        if verbose:
            print(f"processing {issue.key} in epics: {issue.key in epics}")
        # filter out epics
        if issue.key not in epics:
            try:
                epics[issue.fields.customfield_10006]['issues'].append(issue)
                if issue.fields.status.name not in \
                        epics[issue.fields.customfield_10006]['status']:
                    epics[issue.fields.customfield_10006]['status'][
                        issue.fields.status.name] = 1
                else:
                    epics[issue.fields.customfield_10006]['status'][
                        issue.fields.status.name] += 1
            except:
                unassociated.append(issue)

    # data exceptions
    for ignored in ignores:
        if ignored in epics:
            epics.pop(ignored)

    # filter for active epics
    active_epics = [item for item in epics.values()
                    if len(item['issues']) != item['status'].get('Done', 0)
                    and not 'long-term' in item['epic'].fields.labels]

    # filter for long term epics
    long_term_epics = [item for item in epics.values() if
                       'long-term' in item['epic'].fields.labels]

    active_priority_epics = [item for item in active_epics if
                             'Planned' in item['status'].keys() or
                             'In Progress' in item['status'].keys() or
                             'Pending Review' in item['status'].keys()]

    long_term_priority_epics = [item for item in long_term_epics if
                                'Planned' in item['status'].keys() or
                                'In Progress' in item['status'].keys() or
                                'Pending Review' in item['status'].keys()]

    unassociated_status = Counter(
        [item.fields.status.name for item in unassociated])

    other_priority_count = sum([
        unassociated_status.get("Planned", 0),
        unassociated_status.get("In Progress", 0),
        unassociated_status.get("Pending Review", 0)])

    # render report
    content = render_report(template, {
        'unassociated': unassociated,
        'unassociated_status': unassociated_status,
        'epics': epics,
        'long_term_epics': long_term_epics,
        'active_epics': active_epics,
        'priority_epics': active_priority_epics + long_term_priority_epics,
        'other_priority_count': other_priority_count,
        'title': title,
    })

    # write file
    with open(output, 'w') as output_file:
        output_file.write(content)


if __name__ == "__main__":
    roadmap()
