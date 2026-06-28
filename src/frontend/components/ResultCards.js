import ChartCard from '/ui/components/ChartCard.js'
import SqlCard from '/ui/components/SqlCard.js'
import StepsCard from '/ui/components/StepsCard.js'
import TableCard from '/ui/components/TableCard.js'

export default {
  name: 'ResultCards',
  components: { ChartCard, SqlCard, StepsCard, TableCard },
  props: { message: { type: Object, required: true } },
  template: /*html*/`
    <div class="result-cards">
      <SqlCard v-if="message.sql" :sql="message.sql" :cache-hit="!!message.cacheHit" />
      <StepsCard v-if="message.steps && message.steps.length" :steps="message.steps" />
      <ChartCard v-if="message.chartSpec" :spec="message.chartSpec" />
      <TableCard v-if="message.rows && message.rows.length"
                 :columns="message.columns || []"
                 :rows="message.rows"
                 :row-count="message.rowCount || 0"
                 :execution-time-ms="message.executionTimeMs || 0"
                 :viz-hint="message.vizHint || ''"
                 :usage="message.usage" />
    </div>
  `,
}
