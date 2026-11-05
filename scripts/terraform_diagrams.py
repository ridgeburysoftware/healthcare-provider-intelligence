"""Render configuration dependency diagrams for the two historical AWS roots."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terraform', default='terraform')
    parser.add_argument('--dot', default='dot', help='Graphviz dot executable')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output = repo / 'docs/terraform'
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CHECKPOINT_DISABLE='1', TF_IN_AUTOMATION='1')
    for folder, name, title in [
        ('ecs', 'infra-ecs', 'Provider Intelligence | original AWS application infrastructure'),
        ('glue', 'infra-pipeline', 'Provider Intelligence | original AWS data pipeline'),
    ]:
        root = repo / 'infra/aws' / folder
        result = subprocess.run([args.terraform, '-chdir=' + str(root), 'graph', '-no-color'],
                                check=True, capture_output=True, text=True, encoding='utf-8', env=env)
        raw = result.stdout
        (output / (name + '.dot')).write_text(raw, encoding='utf-8', newline='\n')
        styled = raw.replace('digraph G {', 'digraph G {\n  graph [bgcolor="white", label="' + title +
                             '\\nTerraform configuration dependencies — arrows point to dependencies", '
                             'labelloc="t", fontsize=20, fontname="Arial", fontcolor="#071e3d", '
                             'pad=0.35, nodesep=0.22, ranksep=0.6];\n'
                             '  edge [color="#849bb7", arrowsize=0.65];')
        styled = styled.replace('node [shape = rect, fontname = "sans-serif"];',
                                'node [shape=box, style="rounded,filled", fontname="Arial", fontsize=12, '
                                'fillcolor="#eff6ff", color="#b4c9e5", fontcolor="#112e51", margin="0.13,0.08"];')
        subprocess.run([args.dot, '-Tsvg', '-o', str(output / (name + '.svg'))], input=styled,
                       text=True, encoding='utf-8', check=True)
        svg = output / (name + '.svg')
        svg.write_text(svg.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
        print('Generated docs/terraform/' + name + '.svg')


if __name__ == '__main__':
    main()
