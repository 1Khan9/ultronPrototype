// One-off generator for the viewer-facing Ultron command/redeem reference (docx).
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, WidthType, BorderStyle, ShadingType, VerticalAlign,
} = require("docx");

const PURPLE = "6B2FB5", LILAC = "EDE3F7", INK = "1A1330", GREY = "5A5570";
const CONTENT = 10512; // 12240 - 2*864 (0.6" margins)

const cellBorder = { style: BorderStyle.SINGLE, size: 1, color: "DDD3EC" };
const borders = { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder };
const cellMargins = { top: 40, bottom: 40, left: 110, right: 110 };

function hcell(text, w) {
  return new TableCell({
    borders, width: { size: w, type: WidthType.DXA }, margins: cellMargins,
    shading: { fill: PURPLE, type: ShadingType.CLEAR },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ spacing: { before: 0, after: 0 },
      children: [new TextRun({ text, bold: true, color: "FFFFFF", size: 19 })] })],
  });
}
function cmdCell(text, w, fill) {
  return new TableCell({
    borders, width: { size: w, type: WidthType.DXA }, margins: cellMargins,
    shading: { fill, type: ShadingType.CLEAR }, verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ spacing: { before: 0, after: 0 },
      children: [new TextRun({ text, bold: true, color: PURPLE, size: 18, font: "Consolas" })] })],
  });
}
function txtCell(text, w, fill) {
  return new TableCell({
    borders, width: { size: w, type: WidthType.DXA }, margins: cellMargins,
    shading: { fill, type: ShadingType.CLEAR }, verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ spacing: { before: 0, after: 0 },
      children: [new TextRun({ text, color: INK, size: 18 })] })],
  });
}
function row2(a, b, wa, wb, i) {
  const fill = i % 2 ? "F7F3FC" : "FFFFFF";
  return new TableRow({ children: [cmdCell(a, wa, fill), txtCell(b, wb, fill)] });
}

const CMD_W = [3050, CONTENT - 3050];
const commands = [
  ["!points / !balance", "Show how many cores you have."],
  ["!leaderboard", "Top 5 core holders in chat."],
  ["!gamble <amt | all>", "Coin-flip a bet — win pays ~1.8x, lose it all."],
  ["!slots <amt | all>", "Spin 3 reels — a triple match hits the jackpot."],
  ["!wheel", "ONE free spin per stream — always pays out cores."],
  ["!heist <amt>", "Start/join a crew heist; a WIN pays out more than you put in."],
  ["!duel @user <amt>", "Challenge a viewer to a 1v1 for cores."],
  ["!accept", "Accept a duel you were challenged to — winner takes both stakes."],
  ["!raffle  /  !enter", "Join the prize raffle (a mod opens it)."],
  ["!trivia", "Mods start a round — first correct answer wins the prize."],
  ["!give @user <amt>", "Gift some of your cores to another viewer."],
  ["!help", "Ultron lists the commands in chat."],
];

const RDM_W = [3050, CONTENT - 3050];
const redeems = [
  ["Spin the Wheel", "Ultron spins the wheel and credits you the prize."],
  ["Slots", "A slots pull — a triple pays a big core jackpot."],
  ["Heist", "Pull off a solo heist for a core payout."],
  ["Duel", "Duel the house — win and the cores are yours."],
  ["Trivia", "Ultron poses a trivia question to chat."],
  ["Raffle", "Drops you into the running raffle."],
];

function sectionHeader(text) {
  return new Paragraph({
    spacing: { before: 160, after: 70 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 10, color: PURPLE, space: 2 } },
    children: [new TextRun({ text, bold: true, size: 24, color: PURPLE })],
  });
}

const doc = new Document({
  styles: { default: { document: { run: { font: "Arial", size: 18 } } } },
  sections: [{
    properties: { page: {
      size: { width: 12240, height: 15840 },
      margin: { top: 720, right: 864, bottom: 648, left: 864 },
    } },
    children: [
      new Paragraph({ spacing: { after: 10 },
        children: [new TextRun({ text: "ULTRON", bold: true, size: 52, color: PURPLE }),
                   new TextRun({ text: "  —  Commands, Games & Channel-Point Redeems", bold: true, size: 26, color: INK })] }),
      new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: PURPLE, space: 1 } },
        spacing: { after: 100 },
        children: [new TextRun({ text: "Watch to earn cores. Spend them on games. The machine is always watching.", italics: true, size: 19, color: GREY })] }),

      sectionHeader("Chat Commands  (type in chat)"),
      new Table({ width: { size: CONTENT, type: WidthType.DXA }, columnWidths: CMD_W,
        rows: [ new TableRow({ tableHeader: true, children: [hcell("Command", CMD_W[0]), hcell("What it does", CMD_W[1])] }),
                ...commands.map((c, i) => row2(c[0], c[1], CMD_W[0], CMD_W[1], i)) ] }),

      sectionHeader("Channel-Point Redeems  (spend channel points)"),
      new Table({ width: { size: CONTENT, type: WidthType.DXA }, columnWidths: RDM_W,
        rows: [ new TableRow({ tableHeader: true, children: [hcell("Reward", RDM_W[0]), hcell("What happens", RDM_W[1])] }),
                ...redeems.map((c, i) => row2(c[0], c[1], RDM_W[0], RDM_W[1], i)) ] }),

      sectionHeader("How cores work"),
      new Paragraph({ spacing: { after: 40 }, children: [
        new TextRun({ text: "Earn:  ", bold: true, color: PURPLE, size: 18 }),
        new TextRun({ text: "just hang out — you collect cores automatically every minute you're active in chat.", size: 18, color: INK }) ] }),
      new Paragraph({ spacing: { after: 40 }, children: [
        new TextRun({ text: "Spend:  ", bold: true, color: PURPLE, size: 18 }),
        new TextRun({ text: "gamble, run heists, duel, raffle. The games have a house edge (it's for fun) — bet what you're happy to lose.", size: 18, color: INK }) ] }),
      new Paragraph({ children: [
        new TextRun({ text: "Be cool:  ", bold: true, color: PURPLE, size: 18 }),
        new TextRun({ text: "Ultron moderates chat. Keep it clean and the machine leaves you be.", size: 18, color: INK }) ] }),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("docs/twitch_integration/ULTRON_VIEWER_GUIDE.docx", buf);
  console.log("wrote docs/twitch_integration/ULTRON_VIEWER_GUIDE.docx (" + buf.length + " bytes)");
});
