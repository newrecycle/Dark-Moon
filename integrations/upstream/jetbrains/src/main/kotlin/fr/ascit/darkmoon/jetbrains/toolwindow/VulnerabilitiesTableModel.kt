package fr.ascit.darkmoon.jetbrains.toolwindow

import fr.ascit.darkmoon.client.Finding
import fr.ascit.darkmoon.client.Severity
import javax.swing.table.AbstractTableModel

/**
 * Table model for the Vulnerabilities table. Columns (§3.5): severity,
 * title/type, target/component, status, campaign. Rows are redaction-safe
 * findings (no evidence).
 */
class VulnerabilitiesTableModel : AbstractTableModel() {

    private val columns = listOf("Severity", "Title / Type", "Target / Component", "Status", "Campaign")
    private var rows: List<Finding> = emptyList()

    fun setFindings(findings: List<Finding>) {
        rows = findings
        fireTableDataChanged()
    }

    fun findingAt(modelRow: Int): Finding? = rows.getOrNull(modelRow)

    override fun getRowCount(): Int = rows.size
    override fun getColumnCount(): Int = columns.size
    override fun getColumnName(column: Int): String = columns[column]

    override fun getColumnClass(columnIndex: Int): Class<*> =
        if (columnIndex == 0) Severity::class.java else String::class.java

    override fun isCellEditable(rowIndex: Int, columnIndex: Int): Boolean = false

    override fun getValueAt(rowIndex: Int, columnIndex: Int): Any {
        val f = rows[rowIndex]
        return when (columnIndex) {
            0 -> f.severity
            1 -> f.title ?: (f.category ?: "(untitled)")
            2 -> f.endpoint ?: (f.targetId ?: "")
            3 -> f.status.wire
            4 -> f.campaignId ?: ""
            else -> ""
        }
    }

    companion object {
        /** Sort severities most-severe first. */
        val SEVERITY_COMPARATOR: Comparator<Severity> = Comparator { a, b -> b.weight - a.weight }
    }
}
