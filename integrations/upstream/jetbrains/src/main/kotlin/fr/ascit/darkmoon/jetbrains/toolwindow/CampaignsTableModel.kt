package fr.ascit.darkmoon.jetbrains.toolwindow

import fr.ascit.darkmoon.client.Campaign
import javax.swing.table.AbstractTableModel

/** Table model for the Campaigns tab. */
class CampaignsTableModel : AbstractTableModel() {

    private val columns = listOf("Campaign", "Target", "Status", "Risk", "Findings", "Created")
    private var rows: List<Campaign> = emptyList()

    fun setCampaigns(campaigns: List<Campaign>) {
        rows = campaigns
        fireTableDataChanged()
    }

    fun campaignAt(modelRow: Int): Campaign? = rows.getOrNull(modelRow)

    override fun getRowCount(): Int = rows.size
    override fun getColumnCount(): Int = columns.size
    override fun getColumnName(column: Int): String = columns[column]
    override fun isCellEditable(rowIndex: Int, columnIndex: Int): Boolean = false

    override fun getColumnClass(columnIndex: Int): Class<*> =
        if (columnIndex == 4) Integer::class.java else String::class.java

    override fun getValueAt(rowIndex: Int, columnIndex: Int): Any {
        val c = rows[rowIndex]
        return when (columnIndex) {
            0 -> c.id
            1 -> c.target ?: (c.targetId ?: "")
            2 -> c.status.wire
            3 -> c.overallRisk.wire
            4 -> c.severity.total
            5 -> c.createdAt ?: ""
            else -> ""
        }
    }
}
