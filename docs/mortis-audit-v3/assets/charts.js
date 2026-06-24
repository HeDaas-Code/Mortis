// Mortis v3 审计报告 — ECharts 图表
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var green = style.getPropertyValue('--green').trim();
  var red = style.getPropertyValue('--red').trim();
  var yellow = style.getPropertyValue('--yellow').trim();
  var purple = style.getPropertyValue('--purple').trim();

  // --- Chart 1: Growth confidence 生命周期 (Figure 5) ---
  var chart1 = echarts.init(document.getElementById('chart-confidence'), null, { renderer: 'svg' });
  chart1.setOption({
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true },
    legend: {
      data: ['confidence', '触发事件'],
      textStyle: { color: muted, fontSize: 11 },
      top: 5
    },
    grid: { left: 50, right: 30, top: 50, bottom: 60 },
    xAxis: {
      type: 'category',
      data: ['CRYSTALLIZE\n(Light)', 'SIMULATE\n(Medium)', 'RECONCILE\n(冲突)', 'ERODE\n(Deep, 7天)', 'ERODE\n(Deep, 30天)', 'search_growths\n(min_conf)'],
      axisLabel: { color: muted, fontSize: 10, interval: 0 },
      axisLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value',
      min: 0, max: 1,
      name: 'confidence',
      nameTextStyle: { color: muted, fontSize: 11 },
      axisLabel: { color: muted, fontSize: 10 },
      axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [
      {
        name: 'confidence',
        type: 'line',
        data: [0.3, 0.5, 0.25, 0.21, 0.04, null],
        lineStyle: { color: accent, width: 3 },
        itemStyle: { color: accent },
        symbolSize: 10,
        connectNulls: false,
        markLine: {
          symbol: 'none',
          lineStyle: { color: yellow, type: 'dashed', width: 2 },
          data: [{ yAxis: 0.5, name: 'min_confidence 阈值', label: { formatter: 'min_conf=0.5', color: yellow, fontSize: 10 } }]
        },
        markPoint: {
          symbol: 'pin', symbolSize: 45,
          data: [
            { coord: [1, 0.5], value: '提升', itemStyle: { color: green } },
            { coord: [2, 0.25], value: '×0.5', itemStyle: { color: red } },
            { coord: [4, 0.04], value: 'archive', itemStyle: { color: red } }
          ]
        }
      },
      {
        name: '触发事件',
        type: 'scatter',
        data: [[0, 0.3], [1, 0.5], [2, 0.25], [3, 0.21], [4, 0.04]],
        itemStyle: { color: accent2, opacity: 0.6 },
        symbolSize: 8
      }
    ]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // --- Chart 2: Redact 覆盖热力图 (Figure 7) ---
  var chart2 = echarts.init(document.getElementById('chart-redact'), null, { renderer: 'svg' });
  var llmPoints = [
    'TaskRouter.route', 'Step._call_provider', 'Step._call_provider(回传)',
    'associate()', 'score_emotion()', 'seed_check()',
    '_generate_reflection()', '_llm_generate()',
    '_summarize()', '_semantic_rerank()', '_analyze_stats()'
  ];
  var redactFields = ['dream callout', 'emotion 标签', 'subconscious', 'emotional_*', 'warning callout'];
  // 0=未覆盖(红) 1=已覆盖(绿) 2=不适用(灰)
  var heatData = [];
  // #1-3 pipeline 层: 带 growth 但未 redact
  [0,1,2].forEach(function(i) { redactFields.forEach(function(_,j) { heatData.push([j, i, 0]); }); });
  // #4 associate: 发 session 文本, 未 redact
  redactFields.forEach(function(_,j) { heatData.push([j, 3, 0]); });
  // #5 score_emotion: 发 session 全文, 未 redact
  redactFields.forEach(function(_,j) { heatData.push([j, 4, 0]); });
  // #6 seed_check: 发 growth body, 未 redact (P1)
  redactFields.forEach(function(_,j) { heatData.push([j, 5, 0]); });
  // #7 _generate_reflection: 发 session, 未 redact
  redactFields.forEach(function(_,j) { heatData.push([j, 6, 0]); });
  // #8 _llm_generate: 取决于调用方
  redactFields.forEach(function(_,j) { heatData.push([j, 7, 2]); });
  // #9 _summarize: 已覆盖
  redactFields.forEach(function(_,j) { heatData.push([j, 8, 1]); });
  // #10 _semantic_rerank: 已覆盖
  redactFields.forEach(function(_,j) { heatData.push([j, 9, 1]); });
  // #11 _analyze_stats: 仅发统计, 不适用
  redactFields.forEach(function(_,j) { heatData.push([j, 10, 2]); });

  chart2.setOption({
    animation: false,
    tooltip: {
      trigger: 'item',
      appendToBody: true,
      formatter: function(p) {
        var labels = { 0: '未覆盖', 1: '已覆盖', 2: '不适用' };
        return llmPoints[p.value[1]] + '<br/>' + redactFields[p.value[0]] + '<br/>状态: ' + labels[p.value[2]];
      }
    },
    grid: { left: 160, right: 30, top: 30, bottom: 80 },
    xAxis: {
      type: 'category',
      data: redactFields,
      axisLabel: { color: muted, fontSize: 10, rotate: 30 },
      axisLine: { lineStyle: { color: rule } },
      splitArea: { show: false }
    },
    yAxis: {
      type: 'category',
      data: llmPoints,
      axisLabel: { color: muted, fontSize: 10 },
      axisLine: { lineStyle: { color: rule } },
      splitArea: { show: false }
    },
    visualMap: {
      min: 0, max: 2,
      show: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 5,
      itemWidth: 15, itemHeight: 15,
      textStyle: { color: muted, fontSize: 10 },
      inRange: { color: [red, green, muted] },
      categories: ['未覆盖', '已覆盖', '不适用'],
      dimension: 2
    },
    series: [{
      type: 'heatmap',
      data: heatData,
      label: {
        show: true,
        formatter: function(p) {
          var symbols = { 0: '✗', 1: '✓', 2: '—' };
          return symbols[p.value[2]];
        },
        color: ink,
        fontSize: 14,
        fontWeight: 'bold'
      },
      itemStyle: { borderColor: bg2, borderWidth: 2 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } }
    }]
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // --- Chart 3: 审计发现分布 (Figure 11) ---
  var chart3 = echarts.init(document.getElementById('chart-findings'), null, { renderer: 'svg' });
  chart3.setOption({
    animation: false,
    tooltip: { trigger: 'item', appendToBody: true },
    legend: {
      orient: 'vertical',
      right: 10, top: 'center',
      textStyle: { color: muted, fontSize: 11 }
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['40%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: { borderColor: bg2, borderWidth: 2 },
      label: {
        show: true,
        color: ink,
        fontSize: 11,
        formatter: '{b}\n{c} 项'
      },
      labelLine: { lineStyle: { color: rule } },
      data: [
        { value: 13, name: '已修复', itemStyle: { color: green } },
        { value: 1, name: 'CRITICAL 潜在', itemStyle: { color: red } },
        { value: 3, name: 'MEDIUM 潜在', itemStyle: { color: yellow } },
        { value: 2, name: '架构改进', itemStyle: { color: purple } },
        { value: 2, name: '后续优化', itemStyle: { color: muted } }
      ]
    }]
  });
  window.addEventListener('resize', function() { chart3.resize(); });
})();
