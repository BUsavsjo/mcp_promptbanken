// Datakontroll för en CSV-fil, lokalt och utan beroenden (Node 18 eller senare).
//
//   node scripts/profilera.mjs <fil.csv> [--delimiter ;] [--json] [--max-exempel 5]
//
// Skriver en profil: rader, kolumner, typ per kolumn, saknade värden, dubbletter, sammanfattande mått för
// tal och avvikande värden. Filen läses bara lokalt. Ingenting skickas någonstans. Skriptet skriver aldrig ut
// textvärden ur kolumner som ser ut att innehålla personuppgifter.
//
// Tal skrivs med decimalkomma eller decimalpunkt. Tomma värden och "-", "NA", "n/a", "saknas" räknas som saknade.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const MISSING = new Set(['', '-', '–', 'na', 'n/a', 'nan', 'null', 'saknas', 'okänt']);
const PERSONAL_HEADER = /(personnummer|pnr|namn|e-?post|mejl|mail|telefon|mobil|adress|födelse|fodelse|ssn)/i;
const PERSONAL_VALUE = [/\b\d{6,8}[-+]?\d{4}\b/, /[^\s@]+@[^\s@]+\.[^\s@]+/];

/** Delar upp text i rader och fält, med citattecken och valfritt skiljetecken. */
export function parseCsv(text, delimiter) {
  const input = text.replace(/^﻿/, '');
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (quoted) {
      if (c === '"' && input[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === delimiter) {
      row.push(field);
      field = '';
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && input[i + 1] === '\n') i++;
      row.push(field);
      field = '';
      rows.push(row);
      row = [];
    } else field += c;
  }
  if (field !== '' || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter(r => r.some(v => v.trim() !== ''));
}

/** Gissar skiljetecken utifrån första raden: det som förekommer flest gånger utanför citattecken. */
export function detectDelimiter(text) {
  const first = text.replace(/^﻿/, '').split(/\r?\n/, 1)[0] ?? '';
  let best = ',';
  let bestCount = -1;
  for (const d of [';', '\t', ',', '|']) {
    let count = 0;
    let quoted = false;
    for (const c of first) {
      if (c === '"') quoted = !quoted;
      else if (c === d && !quoted) count++;
    }
    if (count > bestCount) {
      best = d;
      bestCount = count;
    }
  }
  return best;
}

const isMissing = v => MISSING.has(v.trim().toLowerCase());

/** Tolkar ett tal. Ger null om det inte är ett tal. Hanterar "1 234,5", "1234.5" och "12 %". */
export function parseNumber(value) {
  const cleaned = value.trim().replace(/\s| /g, '').replace(/%$/, '');
  if (!/^[-+−]?\d+([.,]\d+)?$/.test(cleaned) && !/^[-+−]?\d{1,3}([.,]\d{3})+([.,]\d+)?$/.test(cleaned)) return null;
  let s = cleaned.replace('−', '-');
  const lastComma = s.lastIndexOf(',');
  const lastDot = s.lastIndexOf('.');
  if (lastComma >= 0 && lastDot >= 0) {
    const decimal = lastComma > lastDot ? ',' : '.';
    const thousands = decimal === ',' ? '.' : ',';
    s = s.split(thousands).join('').replace(decimal, '.');
  } else if (lastComma >= 0) s = s.replace(',', '.');
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

const round = (n, d = 2) => (Number.isFinite(n) ? Math.round(n * 10 ** d) / 10 ** d : null);

function quantile(sorted, q) {
  if (sorted.length === 0) return null;
  const pos = (sorted.length - 1) * q;
  const lower = Math.floor(pos);
  const upper = Math.ceil(pos);
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (pos - lower);
}

/** Sammanfattande mått för en lista tal. */
export function summarize(numbers) {
  const sorted = [...numbers].sort((a, b) => a - b);
  const n = sorted.length;
  const sum = sorted.reduce((a, b) => a + b, 0);
  const mean = n ? sum / n : null;
  const variance = n > 1 ? sorted.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1) : null;
  const q1 = quantile(sorted, 0.25);
  const q3 = quantile(sorted, 0.75);
  const iqr = q1 === null ? null : q3 - q1;
  const low = iqr === null ? null : q1 - 1.5 * iqr;
  const high = iqr === null ? null : q3 + 1.5 * iqr;
  return {
    n,
    sum: round(sum),
    min: n ? sorted[0] : null,
    max: n ? sorted[n - 1] : null,
    mean: round(mean),
    median: round(quantile(sorted, 0.5)),
    stdev: variance === null ? null : round(Math.sqrt(variance)),
    q1: round(q1),
    q3: round(q3),
    outlierLimits: iqr === null ? null : [round(low), round(high)],
    outliers: iqr === null ? [] : sorted.filter(v => v < low || v > high),
  };
}

/** Bygger profilen. Tar rader där första raden är rubriker. */
export function profile(rows, { maxExamples = 5 } = {}) {
  if (rows.length === 0) return { rows: 0, columns: [], warnings: ['Filen är tom.'], duplicates: 0 };
  const [header, ...allData] = rows;
  const warnings = [];
  // En sista rad som börjar med Summa/Totalt är en kontrollrad, inte data. Den tas bort före beräkningarna
  // och används i stället för att kontrollera att kolumnsummorna stämmer.
  const lastRow = allData[allData.length - 1];
  const hasTotalRow = lastRow !== undefined && /^(summa|totalt|total|sum)\b/i.test((lastRow[0] ?? '').trim());
  const totalRow = hasTotalRow ? lastRow : null;
  const data = hasTotalRow ? allData.slice(0, -1) : allData;
  const width = header.length;
  const ragged = data.filter(r => r.length !== width).length;
  if (ragged > 0) warnings.push(`${ragged} rader har ett annat antal fält än rubrikraden (${width}). Kontrollera skiljetecken och citattecken.`);

  const seen = new Map();
  let duplicates = 0;
  for (const r of data) {
    const key = JSON.stringify(r);
    if (seen.has(key)) duplicates++;
    seen.set(key, true);
  }
  if (duplicates > 0) warnings.push(`${duplicates} rader är exakta dubbletter av en tidigare rad.`);

  const columns = header.map((name, index) => {
    const values = data.map(r => (r[index] ?? ''));
    const present = values.filter(v => !isMissing(v));
    const numbers = present.map(parseNumber);
    const numeric = present.length > 0 && numbers.every(n => n !== null);
    const mixed = !numeric && numbers.some(n => n !== null);
    const personalByName = PERSONAL_HEADER.test(name);
    const personalByValue = present.some(v => PERSONAL_VALUE.some(re => re.test(v)));
    const personal = personalByName || personalByValue;
    const column = {
      name: name.trim() || `(kolumn ${index + 1})`,
      type: numeric ? 'tal' : mixed ? 'blandad' : 'text',
      missing: values.length - present.length,
      missingShare: values.length ? round((values.length - present.length) / values.length, 3) : 0,
      distinct: new Set(present).size,
      possiblyPersonal: personal,
    };
    if (numeric) column.summary = summarize(numbers);
    if (mixed) {
      const nonNumeric = present.filter((v, i) => numbers[i] === null);
      column.nonNumericCount = nonNumeric.length;
      if (!personal) column.nonNumericExamples = [...new Set(nonNumeric)].slice(0, maxExamples);
    }
    if (!numeric && !mixed && !personal && column.distinct <= 20) {
      const counts = new Map();
      for (const v of present) counts.set(v, (counts.get(v) ?? 0) + 1);
      column.topValues = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, maxExamples);
    }
    if (column.missingShare >= 0.2) warnings.push(`Kolumnen "${column.name}" saknar värde på ${Math.round(column.missingShare * 100)} % av raderna.`);
    if (mixed) warnings.push(`Kolumnen "${column.name}" blandar tal och text (${column.nonNumericCount} icke-numeriska värden). Beräkna inte på den innan den rättats.`);
    if (personal) warnings.push(`Kolumnen "${column.name}" kan innehålla personuppgifter. Avidentifiera eller ta bort den innan analysen, och dela den inte vidare.`);
    return column;
  });

  const totalChecks = [];
  if (totalRow) {
    warnings.push('Sista raden är en summarad. Den ingår inte i beräkningarna och används bara för att kontrollera summorna.');
    columns.forEach((column, index) => {
      const stated = parseNumber(totalRow[index] ?? '');
      if (column.type !== 'tal' || stated === null) return;
      const calculated = column.summary.sum;
      const matches = Math.abs(calculated - stated) <= Math.max(0.01, Math.abs(stated) * 0.0005);
      totalChecks.push({ column: column.name, stated, calculated, matches });
      if (!matches) warnings.push(`Summaraden säger ${stated} för "${column.name}" men raderna summerar till ${calculated}. Kontrollera vilken som är rätt.`);
    });
  }
  return { rows: data.length, columnCount: width, duplicates, columns, warnings, totalRow: Boolean(totalRow), totalChecks };
}

/** Läsbar sammanfattning på svenska. */
export function toMarkdown(result, file = 'fil') {
  const lines = [`# Datakontroll: ${file}`, '', `- Rader (utan rubrik${result.totalRow ? ' och summarad' : ''}): ${result.rows}`, `- Kolumner: ${result.columnCount ?? result.columns.length}`, `- Exakta dubbletter: ${result.duplicates}`, ''];
  if (result.warnings.length) {
    lines.push('## Varningar', ...result.warnings.map(w => `- ${w}`), '');
  } else lines.push('Inga varningar.', '');
  lines.push('## Kolumner', '', '| Kolumn | Typ | Saknas | Unika | Anmärkning |', '| --- | --- | --- | --- | --- |');
  for (const c of result.columns) {
    const note = [];
    if (c.possiblyPersonal) note.push('möjliga personuppgifter');
    if (c.summary) note.push(`n=${c.summary.n}, summa ${c.summary.sum}, medel ${c.summary.mean}, median ${c.summary.median}, min ${c.summary.min}, max ${c.summary.max}${c.summary.outliers.length ? `, ${c.summary.outliers.length} avvikande` : ''}`);
    if (c.topValues) note.push(`vanligast: ${c.topValues.map(([v, n]) => `${v} (${n})`).join(', ')}`);
    lines.push(`| ${c.name} | ${c.type} | ${c.missing} (${Math.round(c.missingShare * 100)} %) | ${c.distinct} | ${note.join('; ')} |`);
  }
  if (result.totalChecks?.length) {
    lines.push('', '## Kontroll mot summarad', '', '| Kolumn | Summarad | Summerat från raderna | Stämmer |', '| --- | --- | --- | --- |');
    for (const c of result.totalChecks) lines.push(`| ${c.column} | ${c.stated} | ${c.calculated} | ${c.matches ? 'ja' : 'nej'} |`);
  }
  lines.push('', 'Avvikande värden är de utanför 1,5 gånger kvartilavståndet. Det är en signal att titta närmare, inte ett fel.');
  return `${lines.join('\n')}\n`;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2);
  const file = args.find(a => !a.startsWith('--') && args[args.indexOf(a) - 1] !== '--delimiter' && args[args.indexOf(a) - 1] !== '--max-exempel');
  if (!file) {
    console.error('Ange en CSV-fil: node scripts/profilera.mjs <fil.csv> [--delimiter ;] [--json]');
    process.exit(2);
  }
  const text = readFileSync(file, 'utf8');
  const at = args.indexOf('--delimiter');
  const delimiter = at >= 0 ? (args[at + 1] === '\\t' ? '\t' : args[at + 1]) : detectDelimiter(text);
  const maxAt = args.indexOf('--max-exempel');
  const result = profile(parseCsv(text, delimiter), { maxExamples: maxAt >= 0 ? Number(args[maxAt + 1]) : 5 });
  console.log(args.includes('--json') ? JSON.stringify({ delimiter, ...result }, null, 2) : toMarkdown(result, file));
}
