import argparse
import logging
from pathlib import Path
from .core import ROOT, convert, g6, merge, read, validate, write

def main():
    parser = argparse.ArgumentParser(description='RAGFlow evidence graph utilities')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('validate')
    p.add_argument('input'); p.add_argument('--formal', action='store_true')
    p = sub.add_parser('convert')
    p.add_argument('--rows', required=True); p.add_argument('--audit', required=True)
    p.add_argument('--decisions'); p.add_argument('--out', default='output')
    p = sub.add_parser('merge')
    p.add_argument('inputs', nargs='+'); p.add_argument('--out', default='output/merged')
    p.add_argument('--aliases', default=str(ROOT / 'config' / 'aliases.json'))
    p = sub.add_parser('g6')
    p.add_argument('input'); p.add_argument('--out', default='output/g6-data.json')
    args = parser.parse_args()
    (ROOT / 'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=ROOT / 'logs' / 'conversion.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        if args.command == 'validate':
            if 'triples' in read(args.input):
                from .export_validation import validate_export
                validate_export(Path(args.input).parent)
            else:
                validate(read(args.input), formal=args.formal)
            print('VALID')
        elif args.command == 'g6':
            write(args.out, g6(read(args.input)))
        elif args.command == 'merge':
            graph = merge([read(p) for p in args.inputs], read(args.aliases))
            write(Path(args.out) / 'graph.json', graph)
            write(Path(args.out) / 'g6-data.json', g6(graph))
        else:
            audit = Path(args.audit)
            graph, review = convert(read(args.rows), read(audit / 'pages.json'), read(audit / 'document.json'),
                                    read(args.decisions) if args.decisions else {}, read(ROOT / 'config' / 'aliases.json'))
            write(Path(args.out) / 'review.json', review)
            if graph['entities'] or graph['relations']:
                write(Path(args.out) / 'graph.json', graph)
                write(Path(args.out) / 'g6-data.json', g6(graph))
                print(f'Actual verified entities={len(graph["entities"])}, approved relations={len(graph["relations"])}')
            else:
                print('No verifiable items: review.json written; no result graph generated.')
        logging.info('Completed %s', args.command)
    except Exception:
        logging.exception('Failed %s', args.command)
        raise

if __name__ == '__main__':
    main()
