<template>
  <div class="patient-portal">
    <!-- 顶部导航 -->
    <el-header class="portal-header">
      <div class="header-left">
        <el-icon size="28" color="#3b82f6"><FirstAidKit /></el-icon>
        <span class="system-name">智慧骨科云平台</span>
        <el-tag size="small" type="info">患者端</el-tag>
      </div>
      <div class="header-right">
        <span class="welcome-text">您好，{{ patientInfo.full_name || patientInfo.username }}</span>
        <el-dropdown @command="handleCommand">
          <el-avatar :size="36" :icon="UserFilled" class="user-avatar" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人信息</el-dropdown-item>
              <el-dropdown-item command="password">修改密码</el-dropdown-item>
              <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <el-container class="portal-container">
      <!-- 左侧菜单 -->
      <el-aside width="220px" class="portal-sidebar">
        <el-menu
          :default-active="activeMenu"
          class="portal-menu"
          @select="handleMenuSelect"
        >
          <el-menu-item index="overview">
            <el-icon><HomeFilled /></el-icon>
            <span>概览</span>
          </el-menu-item>
          <el-menu-item index="records">
            <el-icon><Document /></el-icon>
            <span>我的病历</span>
          </el-menu-item>
          <el-menu-item index="doctors">
            <el-icon><User /></el-icon>
            <span>主治医师</span>
          </el-menu-item>
          <el-menu-item index="reports">
            <el-icon><Files /></el-icon>
            <span>检查报告</span>
          </el-menu-item>
          <el-menu-item index="messages">
            <el-icon><ChatDotRound /></el-icon>
            <span>消息通知</span>
            <el-badge v-if="unreadCount > 0" :value="unreadCount" class="message-badge-menu" />
          </el-menu-item>
        </el-menu>
      </el-aside>

      <!-- 主内容区 -->
      <el-main class="portal-main">
        <!-- 概览页面 -->
        <div v-if="activeMenu === 'overview'" class="page-content">
          <h2 class="page-title">个人概览</h2>

          <!-- 登录信息提示 -->
          <el-alert
            title="登录信息"
            type="info"
            :closable="false"
            style="margin-bottom: 20px;"
          >
            <template #default>
              <div style="display: flex; align-items: center; gap: 20px;">
                <span>用户名：<strong>{{ patientInfo.username }}</strong></span>
                <el-button type="primary" size="small" @click="copyUsername">复制用户名</el-button>
              </div>
            </template>
          </el-alert>

          <!-- 个人信息卡片 -->
          <el-row :gutter="20" class="info-cards">
            <el-col :span="8">
              <el-card class="info-card" shadow="hover">
                <div class="card-header">
                  <el-icon size="32" color="#3b82f6"><User /></el-icon>
                  <span class="card-title">基本信息</span>
                </div>
                <div class="card-content">
                  <p><strong>姓名：</strong>{{ patientInfo.full_name }}</p>
                  <p><strong>性别：</strong>{{ patientProfile.gender }}</p>
                  <p><strong>年龄：</strong>{{ calculateAge(patientProfile.birth_date) }}岁</p>
                  <p><strong>病历号：</strong>{{ patientProfile.patient_number }}</p>
                </div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card class="info-card" shadow="hover">
                <div class="card-header">
                  <el-icon size="32" color="#10b981"><FirstAidKit /></el-icon>
                  <span class="card-title">我的医生</span>
                </div>
                <div class="card-content">
                  <div v-if="myDoctors.length > 0">
                    <div v-for="doctor in myDoctors.slice(0, 2)" :key="doctor.id" class="doctor-item" style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px dashed #e5e7eb;">
                      <p><strong>姓名：</strong>{{ doctor.full_name }} <el-tag v-if="doctor.is_primary" type="success" size="small">主治</el-tag></p>
                      <p><strong>科室：</strong>{{ doctor.department }}</p>
                      <p><strong>职称：</strong>{{ doctor.title }}</p>
                    </div>
                    <div v-if="myDoctors.length > 2" class="more-doctors" style="text-align: center; color: #909399; font-size: 12px;">
                      还有 {{ myDoctors.length - 2 }} 位医生
                    </div>
                  </div>
                  <div v-else class="empty-text">
                    暂无关联医生
                  </div>
                </div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card class="info-card" shadow="hover">
                <div class="card-header">
                  <el-icon size="32" color="#f59e0b"><Document /></el-icon>
                  <span class="card-title">病历统计</span>
                </div>
                <div class="card-content">
                  <div class="stat-item">
                    <span class="stat-number">{{ medicalRecords.length }}</span>
                    <span class="stat-label">病历总数</span>
                  </div>
                  <div class="stat-item">
                    <span class="stat-number">{{ recentRecords.length }}</span>
                    <span class="stat-label">最近30天</span>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>

          <!-- 最近病历 -->
          <el-card class="recent-records" shadow="never">
            <template #header>
              <div class="card-header-with-action">
                <span>最近病历</span>
                <el-link type="primary" @click="activeMenu = 'records'">查看全部</el-link>
              </div>
            </template>
            <el-table :data="recentRecords.slice(0, 5)" style="width: 100%">
              <el-table-column prop="record_number" label="病历号" width="120" />
              <el-table-column label="就诊日期" width="150">
                <template #default="{ row }">
                  {{ formatDate(row.visit_date) }}
                </template>
              </el-table-column>
              <el-table-column prop="doctor_name" label="主治医生" width="120" />
              <el-table-column prop="diagnosis" label="诊断结果" show-overflow-tooltip />
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'active' ? 'success' : 'info'">
                    {{ row.status === 'active' ? '有效' : '已归档' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="100" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewRecordDetail(row)">详情</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>

        <!-- 病历页面 -->
        <div v-if="activeMenu === 'records'" class="page-content">
          <h2 class="page-title">我的病历</h2>
          <el-card shadow="never">
            <el-table :data="medicalRecords" style="width: 100%">
              <el-table-column prop="record_number" label="病历号" width="120" />
              <el-table-column label="就诊日期" width="150">
                <template #default="{ row }">
                  {{ formatDate(row.visit_date) }}
                </template>
              </el-table-column>
              <el-table-column prop="doctor_name" label="主治医生" width="120" />
              <el-table-column prop="diagnosis" label="诊断结果" show-overflow-tooltip />
              <el-table-column prop="treatment" label="治疗方案" show-overflow-tooltip />
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'active' ? 'success' : 'info'">
                    {{ row.status === 'active' ? '有效' : '已归档' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewRecordDetail(row)">查看详情</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>

        <!-- 主治医师页面 -->
        <div v-if="activeMenu === 'doctors'" class="page-content">
          <h2 class="page-title">我的主治医师</h2>
          <el-row :gutter="20">
            <el-col v-for="doctor in myDoctors" :key="doctor.id" :span="12">
              <el-card class="doctor-card" shadow="hover">
                <div class="doctor-header">
                  <el-avatar :size="64" :icon="UserFilled" />
                  <div class="doctor-info">
                    <h3>{{ doctor.full_name }}</h3>
                    <p>{{ doctor.department }} | {{ doctor.title }}</p>
                    <p>{{ doctor.hospital }}</p>
                  </div>
                  <el-tag v-if="doctor.is_primary" type="success">主治医生</el-tag>
                </div>
                <div class="doctor-body">
                  <p><strong>执业证号：</strong>{{ doctor.license_number }}</p>
                  <p><strong>专业特长：</strong>{{ doctor.specialty }}</p>
                  <p><strong>联系电话：</strong>{{ doctor.phone }}</p>
                </div>
                <div class="doctor-footer">
                  <el-button type="primary" @click="contactDoctor(doctor)">联系医生</el-button>
                  <el-button type="success" @click="openMessageDialog(doctor)">
                    <el-icon><ChatDotRound /></el-icon> 发消息
                  </el-button>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </div>

        <!-- 检查报告页面 -->
        <div v-if="activeMenu === 'reports'" class="page-content">
          <h2 class="page-title">检查报告</h2>
          <el-card shadow="never">
            <el-empty v-if="detectionReports.length === 0" description="暂无检查报告" />
            <el-timeline v-else>
              <el-timeline-item
                v-for="report in detectionReports"
                :key="report.id"
                :timestamp="formatDateTime(report.timestamp)"
                placement="top"
              >
                <el-card shadow="hover">
                  <div class="report-header">
                    <h4>骨折检测报告</h4>
                    <div class="report-actions">
                      <el-button type="primary" size="small" @click="viewReportDetail(report)">
                        <el-icon><View /></el-icon>查看详情
                      </el-button>
                      <el-button type="success" size="small" @click="exportReport(report)">
                        <el-icon><Download /></el-icon>导出报告
                      </el-button>
                    </div>
                  </div>
                  <p><strong>检测医生：</strong>{{ report.doctor_name }}</p>
                  <p><strong>检测模型：</strong>{{ report.model_name || report.model }}</p>
                  <p><strong>检测数量：</strong>{{ report.count }}处</p>
                  <p><strong>平均置信度：</strong>{{ (report.confidence * 100).toFixed(2) }}%</p>
                  <p v-if="report.fracture_types && report.fracture_types.length > 0">
                    <strong>骨折类型：</strong>{{ translateFractureTypes(report.fracture_types).join('、') }}
                  </p>
                  <div class="report-images">
                    <el-image
                      v-if="report.original_image"
                      :src="report.original_image"
                      :preview-src-list="[report.original_image, report.result_image]"
                      fit="cover"
                      style="width: 150px; height: 150px; margin-right: 10px;"
                    />
                  </div>
                </el-card>
              </el-timeline-item>
            </el-timeline>
          </el-card>
        </div>

        <!-- 消息通知页面 -->
        <div v-if="activeMenu === 'messages'" class="page-content">
          <h2 class="page-title">消息通知</h2>

          <!-- 系统公告 -->
          <el-card shadow="never" style="margin-bottom: 20px;">
            <template #header>
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <span style="font-weight: 600;">
                  <el-icon style="margin-right: 8px;"><Bell /></el-icon>系统公告
                </span>
                <el-badge v-if="unreadAnnouncementCount > 0" :value="unreadAnnouncementCount" type="danger" />
              </div>
            </template>
            <div v-if="announcements.length === 0" style="text-align: center; padding: 40px; color: #909399;">
              <el-icon :size="48" color="#dcdfe6"><Bell /></el-icon>
              <p style="margin-top: 10px;">暂无系统公告</p>
            </div>
            <div v-else>
              <div
                v-for="announcement in announcements"
                :key="announcement.id"
                class="announcement-item"
                style="padding: 15px; border-bottom: 1px solid #ebeef5; cursor: pointer; transition: background 0.2s;"
                :style="announcement.is_read ? {} : { background: '#f0f9ff' }"
                @click="viewAnnouncement(announcement)"
              >
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                  <el-tag v-if="!announcement.is_read" type="danger" size="small">未读</el-tag>
                  <el-tag :type="getAnnouncementPriorityType(announcement.priority)" size="small">
                    {{ getAnnouncementPriorityLabel(announcement.priority) }}
                  </el-tag>
                  <span style="font-weight: 600; flex: 1;">{{ announcement.title }}</span>
                  <span style="color: #c0c4cc; font-size: 12px;">{{ formatDateTime(announcement.created_at) }}</span>
                </div>
                <div style="color: #606266; font-size: 14px; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
                  {{ announcement.content }}
                </div>
              </div>
            </div>
          </el-card>

          <!-- 医生消息 -->
          <el-card shadow="never" v-loading="contactsLoading">
            <template #header>
              <span style="font-weight: 600;">
                <el-icon style="margin-right: 8px;"><ChatDotRound /></el-icon>医生消息
              </span>
            </template>
            <div v-if="messageContacts.length === 0" class="empty-messages" style="text-align: center; padding: 60px 20px;">
              <el-icon :size="64" color="#dcdfe6"><ChatDotRound /></el-icon>
              <p style="color: #909399; margin-top: 20px;">暂无消息</p>
              <p style="color: #c0c4cc; font-size: 14px;">当医生给您回复消息时，会显示在这里</p>
            </div>
            <div v-else class="message-contacts-list">
              <div
                v-for="contact in messageContacts"
                :key="contact.id"
                class="contact-item"
                style="display: flex; align-items: center; padding: 15px; border-bottom: 1px solid #ebeef5; cursor: pointer; transition: background 0.2s;"
                :style="contact.unread_count > 0 ? { background: '#f0f9ff' } : {}"
                @click="openMessageDialog(contact)"
              >
                <el-avatar :size="50" :icon="UserFilled" style="margin-right: 15px;" />
                <div class="contact-info" style="flex: 1;">
                  <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 5px;">
                    <span style="font-weight: 600; font-size: 16px;">{{ contact.full_name }}</span>
                    <el-tag v-if="contact.is_primary" type="success" size="small">主治医生</el-tag>
                    <el-badge v-if="contact.unread_count > 0" :value="contact.unread_count" type="danger" />
                  </div>
                  <div style="color: #909399; font-size: 14px;">
                    <span v-if="contact.last_message">{{ contact.last_message }}</span>
                    <span v-else>暂无消息</span>
                  </div>
                  <div v-if="contact.last_message_time" style="color: #c0c4cc; font-size: 12px; margin-top: 4px;">
                    {{ formatDateTime(contact.last_message_time) }}
                  </div>
                </div>
                <el-button type="primary" link>
                  <el-icon><ChatDotRound /></el-icon>
                  聊天
                </el-button>
              </div>
            </div>
          </el-card>
        </div>
      </el-main>
    </el-container>

    <!-- 病历详情弹窗 -->
    <el-dialog v-model="recordDetailVisible" title="病历详情" width="700px">
      <el-descriptions :column="2" border v-if="selectedRecord">
        <el-descriptions-item label="病历号">{{ selectedRecord.record_number }}</el-descriptions-item>
        <el-descriptions-item label="就诊日期">{{ formatDate(selectedRecord.visit_date) }}</el-descriptions-item>
        <el-descriptions-item label="主治医生">{{ selectedRecord.doctor_name }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="selectedRecord.status === 'active' ? 'success' : 'info'">
            {{ selectedRecord.status === 'active' ? '有效' : '已归档' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="症状描述" :span="2">{{ selectedRecord.symptoms }}</el-descriptions-item>
        <el-descriptions-item label="诊断结果" :span="2">{{ selectedRecord.diagnosis }}</el-descriptions-item>
        <el-descriptions-item label="治疗方案" :span="2">{{ selectedRecord.treatment }}</el-descriptions-item>
        <el-descriptions-item label="医嘱" :span="2">{{ selectedRecord.advice }}</el-descriptions-item>
        <el-descriptions-item label="处方" :span="2">
          <pre>{{ JSON.stringify(selectedRecord.prescription, null, 2) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="复诊日期">{{ selectedRecord.follow_up_date ? formatDate(selectedRecord.follow_up_date) : '无需复诊' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 检查报告详情弹窗 -->
    <el-dialog v-model="reportDetailVisible" title="检查报告详情" width="800px">
      <div v-if="selectedReport" class="report-detail">
        <!-- 报告基本信息 -->
        <el-card class="detail-section">
          <template #header>
            <span>检测信息</span>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="检测时间">{{ formatDateTime(selectedReport.timestamp) }}</el-descriptions-item>
            <el-descriptions-item label="检测医生">{{ selectedReport.doctor_name }}</el-descriptions-item>
            <el-descriptions-item label="检测模型">{{ selectedReport.model_name || selectedReport.model }}</el-descriptions-item>
            <el-descriptions-item label="骨折数量">{{ selectedReport.count }}处</el-descriptions-item>
            <el-descriptions-item label="平均置信度">{{ (selectedReport.confidence * 100).toFixed(2) }}%</el-descriptions-item>
            <el-descriptions-item label="骨折类型" v-if="selectedReport.fracture_types?.length">
              {{ translateFractureTypes(selectedReport.fracture_types).join('、') }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- AI诊断结果 -->
        <el-card class="detail-section" v-if="selectedReport.detections?.length">
          <template #header>
            <span>AI辅助诊断结果</span>
          </template>
          <el-table :data="selectedReport.detections" style="width: 100%">
            <el-table-column type="index" label="序号" width="60" />
            <el-table-column label="骨折类型">
              <template #default="{ row }">
                {{ getFractureTypeName(row.class) }}
              </template>
            </el-table-column>
            <el-table-column prop="confidence" label="置信度">
              <template #default="{ row }">
                {{ (row.confidence * 100).toFixed(2) }}%
              </template>
            </el-table-column>
            <el-table-column prop="bbox" label="位置坐标">
              <template #default="{ row }">
                [{{ row.bbox?.map(v => v.toFixed(1)).join(', ') }}]
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 医生诊断 -->
        <el-card class="detail-section" v-if="selectedReport.diagnosis">
          <template #header>
            <span>医生诊断</span>
          </template>
          <p class="diagnosis-content">{{ selectedReport.diagnosis }}</p>
        </el-card>

        <!-- 医疗建议 -->
        <el-card class="detail-section" v-if="selectedReport.has_medical_advice && selectedReport.medical_advice">
          <template #header>
            <span>医疗建议</span>
          </template>
          <div v-if="selectedReport.medical_advice && typeof selectedReport.medical_advice === 'object'">
            <!-- 如果有interpretation字段，使用vue-markdown渲染 -->
            <div v-if="selectedReport.medical_advice.interpretation" class="markdown-body medical-advice-content">
              <vue-markdown :source="selectedReport.medical_advice.interpretation" />
            </div>
            <!-- 引用溯源：正文里的 [1][2] 对应的来源 -->
            <CitationList
              v-if="selectedReport.medical_advice.references?.length"
              :references="selectedReport.medical_advice.references"
            />
            <!-- 显示结构化字段 -->
            <div v-else>
              <p v-if="selectedReport.medical_advice.diagnosis"><strong>AI诊断：</strong>{{ selectedReport.medical_advice.diagnosis }}</p>
              <p v-if="selectedReport.medical_advice.treatment"><strong>治疗建议：</strong>{{ selectedReport.medical_advice.treatment }}</p>
              <p v-if="selectedReport.medical_advice.precautions"><strong>注意事项：</strong>{{ selectedReport.medical_advice.precautions }}</p>
            </div>
          </div>
          <p v-else-if="selectedReport.medical_advice" class="diagnosis-content">{{ selectedReport.medical_advice }}</p>
          <p v-else class="text-gray-500">暂无医疗建议</p>
        </el-card>

        <!-- 检查图像 -->
        <el-card class="detail-section">
          <template #header>
            <span>检查图像</span>
          </template>
          <div class="detail-images">
            <div class="image-item" v-if="selectedReport.original_image">
              <p class="image-label">原始图像</p>
              <el-image
                :src="selectedReport.original_image"
                :preview-src-list="[selectedReport.original_image, selectedReport.result_image]"
                fit="contain"
                style="width: 100%; max-height: 400px;"
              />
            </div>
            <div class="image-item" v-if="selectedReport.result_image">
              <p class="image-label">检测结果</p>
              <el-image
                :src="selectedReport.result_image"
                :preview-src-list="[selectedReport.original_image, selectedReport.result_image]"
                fit="contain"
                style="width: 100%; max-height: 400px;"
              />
            </div>
          </div>
        </el-card>
      </div>
      <template #footer>
        <el-button @click="reportDetailVisible = false">关闭</el-button>
        <el-button type="primary" @click="exportReport(selectedReport)">
          <el-icon><Download /></el-icon>导出报告
        </el-button>
      </template>
    </el-dialog>

    <!-- 个人信息弹窗 -->
    <el-dialog v-model="showProfileDialog" title="个人信息" width="600px">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="用户名">{{ patientInfo.username }}</el-descriptions-item>
        <el-descriptions-item label="真实姓名">{{ patientInfo.full_name }}</el-descriptions-item>
        <el-descriptions-item label="病历号">{{ patientProfile.patient_number }}</el-descriptions-item>
        <el-descriptions-item label="性别">{{ patientProfile.gender }}</el-descriptions-item>
        <el-descriptions-item label="出生日期">{{ patientProfile.birth_date }}</el-descriptions-item>
        <el-descriptions-item label="身份证号">{{ patientProfile.id_card }}</el-descriptions-item>
        <el-descriptions-item label="手机号码">{{ patientInfo.phone }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ patientInfo.email }}</el-descriptions-item>
        <el-descriptions-item label="家庭住址" :span="2">{{ patientProfile.address }}</el-descriptions-item>
        <el-descriptions-item label="紧急联系人">{{ patientProfile.emergency_contact }}</el-descriptions-item>
        <el-descriptions-item label="紧急电话">{{ patientProfile.emergency_phone }}</el-descriptions-item>
        <el-descriptions-item label="过敏史" :span="2">{{ patientProfile.allergies }}</el-descriptions-item>
        <el-descriptions-item label="既往病史" :span="2">{{ patientProfile.medical_history }}</el-descriptions-item>
      </el-descriptions>
      <div style="margin-top: 15px; padding: 15px; background: #f0f9ff; border-radius: 4px; border-left: 4px solid #3b82f6;">
        <p style="margin: 0; font-weight: bold; color: #1e40af;">登录信息</p>
        <p style="margin: 8px 0 0 0; font-size: 14px; color: #666;">
          用户名：<strong style="color: #1e40af;">{{ patientInfo.username }}</strong>
        </p>
        <p style="margin: 5px 0 0 0; font-size: 12px; color: #888;">请牢记您的用户名，用于登录患者端</p>
      </div>
      <template #footer>
        <el-button @click="showProfileDialog = false">关闭</el-button>
        <el-button type="primary" @click="openEditProfile">编辑资料</el-button>
      </template>
    </el-dialog>

    <!-- 编辑个人信息弹窗 -->
    <el-dialog v-model="showEditProfileDialog" title="编辑个人信息" width="700px">
      <el-form :model="editProfileForm" label-width="100px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="真实姓名">
              <el-input v-model="editProfileForm.full_name" placeholder="请输入真实姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="性别">
              <el-radio-group v-model="editProfileForm.gender">
                <el-radio value="男">男</el-radio>
                <el-radio value="女">女</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="手机号码">
              <el-input v-model="editProfileForm.phone" placeholder="请输入手机号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="出生日期">
              <el-date-picker v-model="editProfileForm.birth_date" type="date" placeholder="选择出生日期" style="width: 100%" value-format="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="身份证号">
              <el-input v-model="editProfileForm.id_card" placeholder="请输入身份证号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱">
              <el-input v-model="editProfileForm.email" placeholder="请输入邮箱" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="家庭住址">
          <el-input v-model="editProfileForm.address" placeholder="请输入家庭住址" />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="紧急联系人">
              <el-input v-model="editProfileForm.emergency_contact" placeholder="请输入紧急联系人姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="紧急电话">
              <el-input v-model="editProfileForm.emergency_phone" placeholder="请输入紧急联系人电话" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="过敏史">
          <el-input v-model="editProfileForm.allergies" type="textarea" :rows="2" placeholder="请输入过敏史（如有）" />
        </el-form-item>
        <el-form-item label="既往病史">
          <el-input v-model="editProfileForm.medical_history" type="textarea" :rows="2" placeholder="请输入既往病史（如有）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditProfileDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存</el-button>
      </template>
    </el-dialog>

    <!-- 修改密码弹窗 -->
    <el-dialog v-model="showPasswordDialog" title="修改密码" width="400px">
      <el-form :model="passwordForm" label-width="100px">
        <el-form-item label="原密码">
          <el-input v-model="passwordForm.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.newPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="passwordForm.confirmPassword" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPasswordDialog = false">取消</el-button>
        <el-button type="primary" @click="changePassword">确定</el-button>
      </template>
    </el-dialog>

    <!-- 消息对话框 -->
    <el-dialog
      v-model="messageDialogVisible"
      :title="messageDoctor ? `与 ${messageDoctor.full_name} 医生对话` : '发送消息'"
      width="600px"
      :close-on-click-modal="false"
    >
      <!-- 聊天记录区域 -->
      <div
        v-loading="chatLoading"
        class="chat-messages"
        style="max-height: 400px; overflow-y: auto; padding: 15px; background: #f5f5f5; border-radius: 8px; margin-bottom: 15px;"
      >
        <div v-if="chatMessages.length === 0" class="empty-chat" style="text-align: center; color: #999; padding: 40px;">
          <el-icon :size="48" style="margin-bottom: 10px;"><ChatDotRound /></el-icon>
          <p>暂无聊天记录，发送第一条消息开始对话吧</p>
        </div>
        <div
          v-for="msg in chatMessages"
          :key="msg.id"
          :class="['message-item', msg.sender_id === patientInfo?.id ? 'message-sent' : 'message-received']"
          style="margin-bottom: 15px; display: flex; flex-direction: column;"
        >
          <!-- 发送者名称 -->
          <span
            :style="[
              msg.sender_id === patientInfo?.id ? { alignSelf: 'flex-end' } : { alignSelf: 'flex-start' },
              { fontSize: '12px', color: '#666', marginBottom: '4px', fontWeight: 500 }
            ]"
          >
            {{ msg.sender_id === patientInfo?.id ? '我' : (messageDoctor?.full_name || '医生') }}
          </span>
          <div
            :style="[
              msg.sender_id === patientInfo?.id
                ? { alignSelf: 'flex-end', background: '#3b82f6', color: 'white', borderRadius: '12px 12px 2px 12px' }
                : { alignSelf: 'flex-start', background: 'white', color: '#333', borderRadius: '12px 12px 12px 2px' },
              { maxWidth: '70%', padding: '10px 15px', boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }
            ]"
          >
            <p style="margin: 0; line-height: 1.5;">{{ msg.content }}</p>
          </div>
          <span
            :style="[
              msg.sender_id === patientInfo?.id ? { alignSelf: 'flex-end' } : { alignSelf: 'flex-start' },
              { fontSize: '12px', color: '#999', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }
            ]"
          >
            {{ formatDateTime(msg.created_at) }}
            <!-- 已读状态提示 -->
            <template v-if="msg.sender_id === patientInfo?.id">
              <el-icon v-if="msg.is_read" style="color: #10b981; font-size: 14px;"><Check /></el-icon>
              <span v-else style="color: #999; font-size: 11px;">未读</span>
            </template>
          </span>
        </div>
      </div>

      <!-- 发送消息区域 -->
      <div class="message-input-area" style="display: flex; gap: 10px;">
        <el-input
          v-model="messageContent"
          type="textarea"
          :rows="3"
          placeholder="请输入您想对医生说的话..."
          maxlength="500"
          show-word-limit
          @keyup.enter.ctrl="sendMessage"
        />
        <el-button
          type="primary"
          :loading="messageLoading"
          @click="sendMessage"
          style="height: auto;"
        >
          <el-icon><Position /></el-icon>
          发送
        </el-button>
      </div>
      <template #footer>
        <el-button @click="messageDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 公告详情弹窗 -->
    <el-dialog
      v-model="announcementDialogVisible"
      title="公告详情"
      width="600px"
    >
      <div v-if="viewingAnnouncement">
        <h3 style="margin-bottom: 16px; font-size: 18px;">{{ viewingAnnouncement.title }}</h3>
        <div style="margin-bottom: 16px;">
          <el-tag :type="getAnnouncementPriorityType(viewingAnnouncement.priority)" style="margin-right: 8px;">
            {{ getAnnouncementPriorityLabel(viewingAnnouncement.priority) }}
          </el-tag>
          <span style="color: #909399; font-size: 14px;">
            发布时间：{{ formatDateTime(viewingAnnouncement.created_at) }}
          </span>
        </div>
        <div style="line-height: 1.8; white-space: pre-wrap; color: #303133; font-size: 15px; padding: 16px; background: #f5f7fa; border-radius: 8px;">
          {{ viewingAnnouncement.content }}
        </div>
      </div>
    </el-dialog>

    <!-- AI助手组件 -->
    <FloatingAIAssistant ref="aiAssistantRef" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  User, UserFilled, FirstAidKit, HomeFilled, Document,
  Files, ChatDotRound, View, Download, Position, Check, Bell
} from '@element-plus/icons-vue'
import VueMarkdown from 'vue-markdown-render'
import 'github-markdown-css/github-markdown-light.css'
import axios from '../utils/axios'
import CitationList from '../components/CitationList.vue'
import { formatDate, formatDateTime } from '../utils/datetime'
import { clearAuth } from '../utils/auth'
import FloatingAIAssistant from '../components/FloatingAIAssistant.vue'

const router = useRouter()

// 注册组件
const components = {
  VueMarkdown
}

const activeMenu = ref('overview')
const patientInfo = ref({})
const patientProfile = ref({})
const medicalRecords = ref([])
const myDoctors = ref([])
const detectionReports = ref([])
const messages = ref([])
const unreadCount = ref(0)
const messageContacts = ref([])
const contactsLoading = ref(false)

// 公告相关
const announcements = ref([])
const unreadAnnouncementCount = ref(0)
const announcementDialogVisible = ref(false)
const viewingAnnouncement = ref(null)
const recordDetailVisible = ref(false)
const selectedRecord = ref(null)
const reportDetailVisible = ref(false)
const selectedReport = ref(null)
const showProfileDialog = ref(false)
const showEditProfileDialog = ref(false)
const showPasswordDialog = ref(false)
const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})
const editProfileForm = reactive({
  full_name: '',
  phone: '',
  email: '',
  id_card: '',
  gender: '男',
  birth_date: '',
  address: '',
  emergency_contact: '',
  emergency_phone: '',
  allergies: '',
  medical_history: ''
})
const savingProfile = ref(false)

const primaryDoctor = computed(() => {
  return myDoctors.value.find(d => d.is_primary)
})

const recentRecords = computed(() => {
  return medicalRecords.value.slice().sort((a, b) => {
    return new Date(b.visit_date) - new Date(a.visit_date)
  })
})

// 简单的Markdown转HTML函数
const renderMarkdownToHtml = (markdown) => {
  if (!markdown) return ''

  // 先处理代码块（避免内部内容被处理）
  const codeBlocks = []
  let html = markdown.replace(/```([\s\S]*?)```/g, (match) => {
    codeBlocks.push(match)
    return `\x00CODE${codeBlocks.length - 1}\x00`
  })

  // 处理表格
  const lines = html.split('\n')
  let inTable = false
  let tableHtml = ''
  const processedLines = []

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()

    // 表格分隔行 (|---|---|)
    if (/^\|[-:|\s]+\|$/.test(line)) {
      inTable = true
      continue
    }

    // 表格行
    if (line.startsWith('|') && line.endsWith('|')) {
      inTable = true
      const cells = line.slice(1, -1).split('|').map(c => c.trim())
      const isHeader = i === 0 || (i > 0 && /^\|[-:|\s]+\|$/.test(lines[i - 1].trim()))

      if (isHeader && !tableHtml.includes('<thead>')) {
        tableHtml += '<thead><tr>' + cells.map(c => `<th style="background: #3b82f6; color: white; padding: 10px; border: 1px solid #ddd;">${c}</th>`).join('') + '</tr></thead><tbody>'
      } else {
        tableHtml += '<tr>' + cells.map(c => `<td style="padding: 10px; border: 1px solid #ddd;">${c}</td>`).join('') + '</tr>'
      }
      continue
    }

    // 结束表格
    if (inTable && tableHtml) {
      processedLines.push('<table style="width: 100%; border-collapse: collapse; margin: 15px 0;">' + tableHtml + '</tbody></table>')
      tableHtml = ''
      inTable = false
    }

    // 普通行
    if (line) {
      processedLines.push(line)
    }
  }

  // 处理剩余的表格
  if (tableHtml) {
    processedLines.push('<table style="width: 100%; border-collapse: collapse; margin: 15px 0;">' + tableHtml + '</tbody></table>')
  }

  html = processedLines.join('\n')

  // 处理标题
  html = html
    .replace(/^### (.*$)/gim, '<h3 style="color: #3b82f6; margin: 15px 0 10px 0;">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 style="color: #3b82f6; margin: 20px 0 15px 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px;">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 style="color: #1e293b; margin: 25px 0 15px 0;">$1</h1>')

  // 处理引用块
  let inBlockquote = false
  let blockquoteContent = []
  const quoteLines = html.split('\n')
  const quoteProcessedLines = []

  for (const line of quoteLines) {
    const blockquoteMatch = line.match(/^[\s]*>[\s]?(.*)$/)
    if (blockquoteMatch) {
      if (!inBlockquote) {
        inBlockquote = true
        blockquoteContent = []
      }
      blockquoteContent.push(blockquoteMatch[1])
    } else {
      if (inBlockquote) {
        quoteProcessedLines.push(`<blockquote style="background: #f8fafc; border-left: 4px solid #3b82f6; padding: 10px 15px; margin: 10px 0; color: #475569;">${blockquoteContent.join('<br>')}</blockquote>`)
        inBlockquote = false
        blockquoteContent = []
      }
      quoteProcessedLines.push(line)
    }
  }
  // 处理未闭合的引用块
  if (inBlockquote && blockquoteContent.length > 0) {
    quoteProcessedLines.push(`<blockquote style="background: #f8fafc; border-left: 4px solid #3b82f6; padding: 10px 15px; margin: 10px 0; color: #475569;">${blockquoteContent.join('<br>')}</blockquote>`)
  }
  html = quoteProcessedLines.join('\n')

  // 处理列表
  html = html.replace(/^[\s]*[-*+]\s+(.+)$/gim, '<li style="margin: 5px 0; margin-left: 20px;">$1</li>')

  // 处理粗体和斜体
  html = html
    .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')

  // 移除分隔线
  html = html.replace(/^\s*---?\s*$/gim, '')

  // 恢复代码块
  html = html.replace(/\x00CODE(\d+)\x00/g, (match, index) => {
    const code = codeBlocks[parseInt(index)].replace(/```([\s\S]*?)```/, '$1')
    return `<pre style="background: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; margin: 10px 0;"><code>${code}</code></pre>`
  })

  // 引用角标 [1] [2]：与页面上保持一致，打印出来也要看得出这是引用
  // 放在**换行之前**，否则 <br> 会插进标签中间把标记拆开
  html = html.replace(
    /\[(\d{1,2})\]/g,
    (m, n) => `<sup style="color:#0d9488;font-weight:600;">[${n}]</sup>`
  )

  // 处理换行
  html = html.replace(/\n/g, '<br>')

  return html
}

// 打印/导出 HTML 的转义
// 导出的正文里会插入文档派生的文本（如引用来源标题），
// 不转义就是把上传内容直接喂进打印窗口
const escapeHtml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

// 打印版的参考资料小节
const renderReferencesHtml = (references) => {
  if (!Array.isArray(references) || !references.length) return ''
  const items = references.map(ref => `
    <li style="margin-bottom: 8px;">
      《${escapeHtml(ref.doc)}》${escapeHtml(ref.section || '')}${ref.page ? ' 第 ' + escapeHtml(ref.page) + ' 页' : ''}
      <span style="color:#0d9488;font-size:12px;">（${escapeHtml(ref.origin_label || ref.origin || '来源')}）</span>
      <div style="color:#475569;font-size:12px;margin-top:4px;white-space:pre-wrap;">${escapeHtml(ref.snippet || '')}</div>
    </li>`).join('')
  return `
    <div class="section">
      <div class="section-title">参考资料</div>
      <ol style="padding-left: 20px;">${items}</ol>
    </div>`
}

const calculateAge = (birthDate) => {
  if (!birthDate) return '-'
  const birth = new Date(birthDate)
  const today = new Date()
  let age = today.getFullYear() - birth.getFullYear()
  const monthDiff = today.getMonth() - birth.getMonth()
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
    age--
  }
  return age
}

// 骨折类型中英文映射（根据 data.yaml 中的实际类型）
const fractureTypeMap = {
  'Avlusion Fracture': '撕脱骨折',
  'Comminuted Fracture': '粉碎性骨折',
  'Compression-Crush Fracutre': '压缩性骨折',
  'Fracture Dislocation': '骨折脱位',
  'GreenStick Fracture': '青枝骨折',
  'HairLine Fracture': '发线骨折',
  'Impact Fracture': '撞击性骨折',
  'Intra-articular fracture': '关节内骨折',
  'Null': '无骨折',
  'Oblique fracture': '斜形骨折',
  'spiral fracture': '螺旋形骨折'
}

// 获取骨折类型的中文名称
const getFractureTypeName = (enName) => {
  return fractureTypeMap[enName] || enName
}

// 翻译骨折类型数组
const translateFractureTypes = (types) => {
  if (!types || !types.length) return []
  return types.map(type => getFractureTypeName(type))
}

// 消息轮询定时器
let messagePollingTimer = null

// 获取未读消息数和联系人列表
const fetchUnreadCount = async () => {
  contactsLoading.value = true
  try {
    const response = await axios.get('/api/messages/contacts')
    if (response.data.success) {
      const contacts = response.data.contacts || []
      messageContacts.value = contacts
      const newUnreadCount = contacts.reduce((sum, contact) => sum + (contact.unread_count || 0), 0)

      // 如果有新消息，显示通知
      if (newUnreadCount > unreadCount.value && unreadCount.value > 0) {
        ElMessage({
          message: `您有 ${newUnreadCount - unreadCount.value} 条新消息`,
          type: 'info',
          duration: 3000
        })
      }

      unreadCount.value = newUnreadCount
    }
  } catch (error) {
    console.error('获取未读消息数失败:', error)
  } finally {
    contactsLoading.value = false
  }
}

// 开始消息轮询
const startMessagePolling = () => {
  // 立即获取一次
  fetchUnreadCount()
  // 每30秒轮询一次
  messagePollingTimer = setInterval(fetchUnreadCount, 30000)
}

// 停止消息轮询
const stopMessagePolling = () => {
  if (messagePollingTimer) {
    clearInterval(messagePollingTimer)
    messagePollingTimer = null
  }
  if (announcementPollingTimer) {
    clearInterval(announcementPollingTimer)
    announcementPollingTimer = null
  }
}

// 获取公告列表
const fetchAnnouncements = async () => {
  try {
    const response = await axios.get('/api/announcements')
    if (response.data.success) {
      announcements.value = response.data.announcements || []
      unreadAnnouncementCount.value = announcements.value.filter(a => !a.is_read).length
    }
  } catch (error) {
    console.error('获取公告失败:', error)
  }
}

// 获取未读公告数量
const fetchUnreadAnnouncementCount = async () => {
  try {
    const response = await axios.get('/api/announcements/unread-count')
    if (response.data.success) {
      unreadAnnouncementCount.value = response.data.unread_count || 0
    }
  } catch (error) {
    console.error('获取未读公告数失败:', error)
  }
}

// 查看公告详情
const viewAnnouncement = async (announcement) => {
  viewingAnnouncement.value = announcement
  announcementDialogVisible.value = true

  // 标记为已读
  if (!announcement.is_read) {
    try {
      await axios.post(`/api/announcements/${announcement.id}/read`)
      announcement.is_read = true
      unreadAnnouncementCount.value = Math.max(0, unreadAnnouncementCount.value - 1)
    } catch (error) {
      console.error('标记公告已读失败:', error)
    }
  }
}

// 获取公告优先级标签
const getAnnouncementPriorityLabel = (priority) => {
  const labels = { low: '低', normal: '普通', high: '高', urgent: '紧急' }
  return labels[priority] || priority
}

// 获取公告优先级类型
const getAnnouncementPriorityType = (priority) => {
  const types = { low: 'info', normal: 'success', high: 'warning', urgent: 'danger' }
  return types[priority] || 'info'
}

// 开始公告轮询
const startAnnouncementPolling = () => {
  fetchAnnouncements()
  announcementPollingTimer = setInterval(fetchAnnouncements, 60000) // 每分钟轮询一次
}

// 公告轮询定时器
let announcementPollingTimer = null

const fetchPatientData = async () => {
  try {
    // 获取患者基本信息
    const userRes = await axios.get('/api/patient/profile')
    patientInfo.value = userRes.data.user || {}
    patientProfile.value = userRes.data.profile || {}

    // 获取病历列表
    const recordsRes = await axios.get('/api/patient/medical-records')
    medicalRecords.value = recordsRes.data.records || []

    // 获取主治医师列表
    const doctorsRes = await axios.get('/api/patient/doctors')
    myDoctors.value = doctorsRes.data.doctors || []

    // 获取检查报告
    const reportsRes = await axios.get('/api/patient/detection-reports')
    detectionReports.value = reportsRes.data.reports || []

    // 获取未读消息数
    await fetchUnreadCount()
  } catch (err) {
    console.error('获取患者数据失败:', err)
    ElMessage.error('获取数据失败')
  }
}

const handleMenuSelect = (index) => {
  activeMenu.value = index
}

const handleCommand = (command) => {
  switch (command) {
    case 'profile':
      showProfileDialog.value = true
      break
    case 'password':
      showPasswordDialog.value = true
      break
    case 'logout':
      handleLogout()
      break
  }
}

const handleLogout = () => {
  ElMessageBox.confirm('确定要退出登录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    clearAuth()
    router.push('/login')
    ElMessage.success('已退出登录')
  })
}

const viewRecordDetail = (record) => {
  selectedRecord.value = record
  recordDetailVisible.value = true
}

// 消息对话框相关
const messageDialogVisible = ref(false)
const messageDoctor = ref(null)
const messageContent = ref('')
const messageLoading = ref(false)
const chatMessages = ref([])
const chatLoading = ref(false)

// 打开消息对话框
const openMessageDialog = (doctor) => {
  messageDoctor.value = doctor
  messageContent.value = ''
  messageDialogVisible.value = true
  // 加载聊天记录
  loadChatHistory(doctor.id)
}

// 加载聊天记录
const loadChatHistory = async (doctorId) => {
  chatLoading.value = true
  try {
    const response = await axios.get(`/api/messages/conversation/${doctorId}`)
    if (response.data.success) {
      chatMessages.value = response.data.messages || []
      // 检查是否有对方发送的未读消息
      const hasUnreadFromDoctor = chatMessages.value.some(
        msg => msg.sender_id === doctorId && !msg.is_read
      )
      // 只有存在对方发送的未读消息时才标记为已读
      if (hasUnreadFromDoctor) {
        await axios.post('/api/messages/mark-read', { sender_id: doctorId })
        // 刷新未读消息数
        await fetchUnreadCount()
      }
    }
  } catch (error) {
    console.error('加载聊天记录失败:', error)
  } finally {
    chatLoading.value = false
  }
}

// 发送消息
const sendMessage = async () => {
  if (!messageContent.value.trim()) {
    ElMessage.warning('请输入消息内容')
    return
  }
  if (!messageDoctor.value) {
    ElMessage.error('请选择医生')
    return
  }

  messageLoading.value = true
  try {
    const response = await axios.post('/api/messages/send', {
      receiver_id: messageDoctor.value.id,
      content: messageContent.value.trim()
    })

    if (response.data.success) {
      ElMessage.success('发送成功')
      messageContent.value = ''
      // 刷新聊天记录
      await loadChatHistory(messageDoctor.value.id)
    } else {
      ElMessage.error(response.data.error || '发送失败')
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    ElMessage.error(error.response?.data?.error || '发送失败')
  } finally {
    messageLoading.value = false
  }
}

const contactDoctor = (doctor) => {
  // 显示医生联系方式对话框
  const phone = doctor.phone || doctor.user?.phone || '暂无电话'
  const email = doctor.email || doctor.user?.email || '暂无邮箱'
  const hospital = doctor.hospital || '未知医院'
  const department = doctor.department || '未知科室'

  ElMessageBox.alert(
    `<div style="padding: 10px;">
      <p><strong>医生姓名：</strong>${doctor.full_name}</p>
      <p><strong>所属医院：</strong>${hospital}</p>
      <p><strong>科室：</strong>${department}</p>
      <p><strong>职称：</strong>${doctor.title || '医生'}</p>
      <hr style="margin: 15px 0; border: none; border-top: 1px solid #e5e7eb;">
      <p><strong>联系电话：</strong><a href="tel:${phone}" style="color: #3b82f6; text-decoration: none;">${phone}</a></p>
      <p><strong>电子邮箱：</strong><a href="mailto:${email}" style="color: #3b82f6; text-decoration: none;">${email}</a></p>
    </div>`,
    '医生联系方式',
    {
      dangerouslyUseHTMLString: true,
      confirmButtonText: '关闭',
      callback: () => {
        ElMessage.success('如需紧急联系，请直接拨打电话')
      }
    }
  )
}

// 查看报告详情
const viewReportDetail = (report) => {
  selectedReport.value = report
  reportDetailVisible.value = true
}

// 导出检查报告为PDF
const exportReport = async (report) => {
  if (!report) return

  // 创建临时容器来生成PDF内容
  const container = document.createElement('div')
  container.className = 'pdf-report-container'
  container.style.cssText = `
    width: 210mm;
    padding: 20mm;
    background: white;
    font-family: 'Microsoft YaHei', 'SimHei', sans-serif;
  `

  // 构建PDF内容HTML
  const medicalAdviceHtml = report.medical_advice && typeof report.medical_advice === 'object' && report.medical_advice.interpretation
    ? report.medical_advice.interpretation.replace(/\n/g, '<br>')
    : (report.medical_advice || '')

  const detectionsHtml = report.detections?.length
    ? report.detections.map((d, i) => `
      <tr>
        <td style="border: 1px solid #ddd; padding: 8px;">${i + 1}</td>
        <td style="border: 1px solid #ddd; padding: 8px;">${getFractureTypeName(d.class)}</td>
        <td style="border: 1px solid #ddd; padding: 8px;">${(d.confidence * 100).toFixed(2)}%</td>
      </tr>
    `).join('')
    : ''

  container.innerHTML = `
    <div style="text-align: center; margin-bottom: 30px; border-bottom: 3px solid #3b82f6; padding-bottom: 20px;">
      <h1 style="color: #1e293b; margin: 0; font-size: 28px;">骨折检测报告</h1>
      <p style="color: #64748b; margin: 10px 0 0 0;">智慧骨科云平台</p>
    </div>

    <div style="margin-bottom: 25px;">
      <h2 style="color: #3b82f6; font-size: 18px; border-left: 4px solid #3b82f6; padding-left: 10px; margin-bottom: 15px;">基本信息</h2>
      <table style="width: 100%; border-collapse: collapse;">
        <tr>
          <td style="padding: 8px; width: 30%; color: #64748b;">检测时间</td>
          <td style="padding: 8px; font-weight: 500;">${formatDateTime(report.timestamp)}</td>
        </tr>
        <tr style="background: #f8fafc;">
          <td style="padding: 8px; color: #64748b;">检测医生</td>
          <td style="padding: 8px; font-weight: 500;">${report.doctor_name || 'AI自动检测'}</td>
        </tr>
        <tr>
          <td style="padding: 8px; color: #64748b;">检测模型</td>
          <td style="padding: 8px; font-weight: 500;">${report.model_name || report.model || '未知'}</td>
        </tr>
        <tr style="background: #f8fafc;">
          <td style="padding: 8px; color: #64748b;">骨折数量</td>
          <td style="padding: 8px; font-weight: 500;">${report.count}处</td>
        </tr>
        <tr>
          <td style="padding: 8px; color: #64748b;">平均置信度</td>
          <td style="padding: 8px; font-weight: 500;">${(report.confidence * 100).toFixed(2)}%</td>
        </tr>
        ${report.fracture_types?.length ? `
        <tr style="background: #f8fafc;">
          <td style="padding: 8px; color: #64748b;">骨折类型</td>
          <td style="padding: 8px; font-weight: 500;">${translateFractureTypes(report.fracture_types).join('、')}</td>
        </tr>
        ` : ''}
      </table>
    </div>

    ${report.detections?.length ? `
    <div style="margin-bottom: 25px;">
      <h2 style="color: #3b82f6; font-size: 18px; border-left: 4px solid #3b82f6; padding-left: 10px; margin-bottom: 15px;">AI辅助诊断结果</h2>
      <table style="width: 100%; border-collapse: collapse;">
        <thead>
          <tr style="background: #3b82f6; color: white;">
            <th style="border: 1px solid #ddd; padding: 10px; text-align: left;">序号</th>
            <th style="border: 1px solid #ddd; padding: 10px; text-align: left;">骨折类型</th>
            <th style="border: 1px solid #ddd; padding: 10px; text-align: left;">置信度</th>
          </tr>
        </thead>
        <tbody>
          ${detectionsHtml}
        </tbody>
      </table>
    </div>
    ` : ''}

    ${report.diagnosis ? `
    <div style="margin-bottom: 25px;">
      <h2 style="color: #3b82f6; font-size: 18px; border-left: 4px solid #3b82f6; padding-left: 10px; margin-bottom: 15px;">医生诊断</h2>
      <div style="background: #f8fafc; padding: 15px; border-radius: 8px; line-height: 1.8;">
        ${report.diagnosis.replace(/\n/g, '<br>')}
      </div>
    </div>
    ` : ''}

    ${report.has_medical_advice && medicalAdviceHtml ? `
    <div style="margin-bottom: 25px;">
      <h2 style="color: #3b82f6; font-size: 18px; border-left: 4px solid #3b82f6; padding-left: 10px; margin-bottom: 15px;">医疗建议</h2>
      <div style="background: #f0fdf4; padding: 15px; border-radius: 8px; line-height: 1.8; border-left: 4px solid #22c55e;">
        ${medicalAdviceHtml}
      </div>
    </div>
    ` : ''}

    <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center; color: #94a3b8; font-size: 12px;">
      <p>本报告由智慧骨科云平台自动生成</p>
      <p>报告编号：${report.id} | 生成时间：${new Date().toLocaleString('zh-CN')}</p>
    </div>
  `

  // 添加到body但隐藏
  container.style.position = 'absolute'
  container.style.left = '-9999px'
  document.body.appendChild(container)

  // 配置PDF选项
  const opt = {
    margin: 0,
    filename: `骨折检测报告_${report.id}_${new Date().toISOString().slice(0, 10)}.pdf`,
    image: { type: 'jpeg', quality: 0.98 },
    html2canvas: { scale: 2, useCORS: true },
    jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
  }

  // 使用浏览器打印功能生成PDF
  const printWindow = window.open('', '_blank')
  if (!printWindow) {
    ElMessage.error('请允许弹出窗口以导出报告')
    return
  }

  printWindow.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <title>骨折检测报告</title>
      <style>
        @page { size: A4; margin: 20mm; }
        body {
          font-family: 'Microsoft YaHei', 'SimHei', sans-serif;
          font-size: 14px;
          line-height: 1.6;
          color: #333;
          max-width: 210mm;
          margin: 0 auto;
          padding: 20mm;
        }
        .header {
          text-align: center;
          margin-bottom: 30px;
          border-bottom: 3px solid #3b82f6;
          padding-bottom: 20px;
        }
        .header h1 {
          color: #1e293b;
          margin: 0;
          font-size: 28px;
        }
        .header p {
          color: #64748b;
          margin: 10px 0 0 0;
        }
        .section {
          margin-bottom: 25px;
        }
        .section-title {
          color: #3b82f6;
          font-size: 18px;
          border-left: 4px solid #3b82f6;
          padding-left: 10px;
          margin-bottom: 15px;
          font-weight: bold;
        }
        table {
          width: 100%;
          border-collapse: collapse;
        }
        td, th {
          padding: 10px;
          text-align: left;
        }
        th {
          background: #3b82f6;
          color: white;
        }
        tr:nth-child(even) {
          background: #f8fafc;
        }
        .info-label {
          color: #64748b;
          width: 30%;
        }
        .info-value {
          font-weight: 500;
        }
        .diagnosis-box {
          background: #f8fafc;
          padding: 15px;
          border-radius: 8px;
          line-height: 1.8;
          white-space: pre-wrap;
        }
        .advice-box {
          background: #f0fdf4;
          padding: 15px;
          border-radius: 8px;
          line-height: 1.8;
          border-left: 4px solid #22c55e;
          white-space: pre-wrap;
        }
        .footer {
          margin-top: 40px;
          padding-top: 20px;
          border-top: 1px solid #e5e7eb;
          text-align: center;
          color: #94a3b8;
          font-size: 12px;
        }
        @media print {
          body { padding: 0; }
          .no-print { display: none; }
        }
      </style>
    </head>
    <body>
      <div class="header">
        <h1>骨折检测报告</h1>
        <p>智慧骨科云平台</p>
      </div>

      <div class="section">
        <div class="section-title">基本信息</div>
        <table>
          <tr>
            <td class="info-label">检测时间</td>
            <td class="info-value">${formatDateTime(report.timestamp)}</td>
          </tr>
          <tr>
            <td class="info-label">检测医生</td>
            <td class="info-value">${report.doctor_name || 'AI自动检测'}</td>
          </tr>
          <tr>
            <td class="info-label">检测模型</td>
            <td class="info-value">${report.model_name || report.model || '未知'}</td>
          </tr>
          <tr>
            <td class="info-label">骨折数量</td>
            <td class="info-value">${report.count}处</td>
          </tr>
          <tr>
            <td class="info-label">平均置信度</td>
            <td class="info-value">${(report.confidence * 100).toFixed(2)}%</td>
          </tr>
          ${report.fracture_types?.length ? `
          <tr>
            <td class="info-label">骨折类型</td>
            <td class="info-value">${translateFractureTypes(report.fracture_types).join('、')}</td>
          </tr>
          ` : ''}
        </table>
      </div>

      ${report.detections?.length ? `
      <div class="section">
        <div class="section-title">AI辅助诊断结果</div>
        <table>
          <thead>
            <tr>
              <th>序号</th>
              <th>骨折类型</th>
              <th>置信度</th>
            </tr>
          </thead>
          <tbody>
            ${report.detections.map((d, i) => `
              <tr>
                <td>${i + 1}</td>
                <td>${getFractureTypeName(d.class)}</td>
                <td>${(d.confidence * 100).toFixed(2)}%</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
      ` : ''}

      ${report.diagnosis ? `
      <div class="section">
        <div class="section-title">医生诊断</div>
        <div class="diagnosis-box">${report.diagnosis.replace(/\n/g, '<br>')}</div>
      </div>
      ` : ''}

      ${report.has_medical_advice && report.medical_advice?.interpretation ? `
      <div class="section">
        <div class="section-title">医疗建议</div>
        <div class="advice-box markdown-content">${renderMarkdownToHtml(report.medical_advice.interpretation)}</div>
      </div>
      ` : ''}

      ${report.medical_advice?.references?.length
        ? renderReferencesHtml(report.medical_advice.references) : ''}

      <div class="footer">
        <p>本报告由智慧骨科云平台自动生成</p>
        <p>报告编号：${report.id} | 生成时间：${new Date().toLocaleString('zh-CN')}</p>
      </div>

      <div class="no-print" style="text-align: center; margin-top: 30px; padding: 20px;">
        <button onclick="window.print()" style="
          background: #3b82f6;
          color: white;
          border: none;
          padding: 12px 30px;
          font-size: 16px;
          border-radius: 6px;
          cursor: pointer;
        ">打印/保存为PDF</button>
        <p style="color: #64748b; margin-top: 10px; font-size: 12px;">
          提示：点击按钮后，在打印对话框中选择"另存为PDF"即可下载报告
        </p>
      </div>
    </body>
    </html>
  `)

  printWindow.document.close()
  ElMessage.success('报告预览已打开，请打印或保存为PDF')
}

// 标记消息为已读
const markMessageAsRead = async (msg) => {
  if (msg.is_read) return
  
  try {
    await axios.put(`/api/patient/messages/${msg.id}/read`)
    msg.is_read = true
    unreadCount.value = messages.value.filter(m => !m.is_read).length
    ElMessage.success('已标记为已读')
  } catch (err) {
    console.error('标记已读失败:', err)
  }
}

const changePassword = async () => {
  if (!passwordForm.oldPassword || !passwordForm.newPassword || !passwordForm.confirmPassword) {
    ElMessage.warning('请填写所有密码字段')
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    ElMessage.error('两次输入的新密码不一致')
    return
  }
  if (passwordForm.newPassword.length < 6) {
    ElMessage.error('新密码至少6位')
    return
  }
  try {
    await axios.post('/api/change-password', {
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword
    })
    ElMessage.success('密码修改成功')
    showPasswordDialog.value = false
    passwordForm.oldPassword = ''
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '修改失败')
  }
}

const openEditProfile = () => {
  // 填充表单数据
  editProfileForm.full_name = patientInfo.value.full_name || ''
  editProfileForm.phone = patientInfo.value.phone || ''
  editProfileForm.email = patientInfo.value.email || ''
  editProfileForm.id_card = patientProfile.value.id_card || ''
  editProfileForm.gender = patientProfile.value.gender || '男'
  editProfileForm.birth_date = patientProfile.value.birth_date || ''
  editProfileForm.address = patientProfile.value.address || ''
  editProfileForm.emergency_contact = patientProfile.value.emergency_contact || ''
  editProfileForm.emergency_phone = patientProfile.value.emergency_phone || ''
  editProfileForm.allergies = patientProfile.value.allergies || ''
  editProfileForm.medical_history = patientProfile.value.medical_history || ''
  
  showProfileDialog.value = false
  showEditProfileDialog.value = true
}

const saveProfile = async () => {
  // 表单验证
  if (!editProfileForm.full_name.trim()) {
    ElMessage.warning('请输入真实姓名')
    return
  }
  if (editProfileForm.phone && !/^1[3-9]\d{9}$/.test(editProfileForm.phone)) {
    ElMessage.warning('手机号格式不正确')
    return
  }
  
  savingProfile.value = true
  try {
    await axios.put('/api/patient/profile/update', editProfileForm)
    ElMessage.success('个人信息更新成功')
    showEditProfileDialog.value = false
    fetchPatientData() // 刷新数据
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '更新失败')
  } finally {
    savingProfile.value = false
  }
}

// 复制用户名到剪贴板
const copyUsername = () => {
  navigator.clipboard.writeText(patientInfo.value.username).then(() => {
    ElMessage.success('用户名已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败，请手动复制')
  })
}

onMounted(() => {
  fetchPatientData()
  startMessagePolling()
  startAnnouncementPolling()
})

onUnmounted(() => {
  stopMessagePolling()
})
</script>

<style scoped>
.patient-portal {
  min-height: 100vh;
  background: #f5f7fa;
}

.portal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: white;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 30px;
  height: 64px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.system-name {
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.welcome-text {
  color: #64748b;
}

.user-avatar {
  cursor: pointer;
}

.portal-container {
  height: calc(100vh - 64px);
}

.portal-sidebar {
  background: white;
  border-right: 1px solid #e4e7ed;
}

.portal-menu {
  border-right: none;
  padding: 20px 0;
}

.message-badge-menu {
  margin-left: 16px;
  position: relative;
  display: inline-flex;
  align-items: center;
}

.message-badge-menu :deep(.el-badge__content) {
  position: absolute;
  top: -8px;
  right: -12px;
  transform: translate(0, 0);
}

.portal-main {
  padding: 30px;
  overflow-y: auto;
}

.page-title {
  margin-bottom: 24px;
  color: #1e293b;
  font-size: 24px;
  font-weight: 600;
}

.info-cards {
  margin-bottom: 24px;
}

.info-card {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}

.card-content p {
  margin: 8px 0;
  color: #64748b;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
}

.stat-number {
  font-size: 32px;
  font-weight: 700;
  color: #3b82f6;
}

.stat-label {
  color: #94a3b8;
  margin-top: 4px;
}

.recent-records {
  margin-top: 24px;
}

.card-header-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.empty-text {
  color: #94a3b8;
  text-align: center;
  padding: 20px 0;
}

.doctor-card {
  margin-bottom: 20px;
}

.doctor-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.doctor-info h3 {
  margin: 0 0 4px 0;
  color: #1e293b;
}

.doctor-info p {
  margin: 2px 0;
  color: #64748b;
  font-size: 14px;
}

.doctor-body {
  margin: 16px 0;
}

.doctor-body p {
  margin: 8px 0;
  color: #64748b;
}

.doctor-footer {
  text-align: right;
}

.report-images {
  margin-top: 12px;
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.report-header h4 {
  margin: 0;
  color: #1e293b;
}

.report-actions {
  display: flex;
  gap: 8px;
}

/* 报告详情样式 */
.report-detail {
  max-height: 600px;
  overflow-y: auto;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.diagnosis-content {
  line-height: 1.8;
  color: #374151;
  white-space: pre-wrap;
}

.medical-advice-content {
  max-height: 500px;
  overflow-y: auto;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.6;
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4 {
  margin-top: 16px;
  margin-bottom: 12px;
}

.markdown-body p {
  margin-bottom: 10px;
}

.markdown-body table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
}

.markdown-body th,
.markdown-body td {
  border: 1px solid #e5e7eb;
  padding: 8px 12px;
  text-align: left;
}

.markdown-body th {
  background-color: #f9fafb;
  font-weight: 600;
}

.detail-images {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.image-item {
  text-align: center;
}

.image-label {
  margin-bottom: 10px;
  font-weight: 600;
  color: #4b5563;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message-item {
  cursor: pointer;
  transition: transform 0.2s;
}

.message-item:hover {
  transform: translateX(4px);
}

.message-card {
  margin-bottom: 0;
  transition: all 0.3s;
}

.message-card.unread {
  border-left: 4px solid #3b82f6;
  background-color: #f0f9ff;
}

.message-card:not(.unread) {
  border-left: 4px solid #e5e7eb;
  opacity: 0.85;
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.message-title-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.message-title {
  font-weight: 600;
  color: #1e293b;
}

.unread-tag {
  font-size: 12px;
}

.read-tag {
  font-size: 12px;
}

.message-title {
  font-weight: 600;
  color: #1e293b;
}

.message-time {
  color: #94a3b8;
  font-size: 13px;
}

.message-content {
  color: #64748b;
  line-height: 1.6;
}
</style>
