pipeline {
  agent { label 'docker' }

  options {
    disableConcurrentBuilds()
    skipDefaultCheckout(true)
    timestamps()
    timeout(time: 45, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  environment {
    DEPLOY_PROJECT_NAME = 'financial-freedom'
    // Jenkins container'inda ve Docker host'ta ayni mutlak yol mount edilmelidir.
    DEPLOY_DIR = '/AppData/financial-freedom'
    API_IMAGE = "financial-freedom-api:${GIT_COMMIT}"
    UI_IMAGE = "financial-freedom-ui:${GIT_COMMIT}"
    DOCKER_BUILDKIT = '1'
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
        script {
          env.GIT_COMMIT = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
          env.API_IMAGE = "financial-freedom-api:${env.GIT_COMMIT}"
          env.UI_IMAGE = "financial-freedom-ui:${env.GIT_COMMIT}"
        }
      }
    }

    stage('Tests and production builds') {
      steps {
        sh 'chmod +x scripts/ci/*.sh && scripts/ci/test.sh'
      }
      post {
        always {
          junit allowEmptyResults: true, testResults: 'test-results/**/*-junit.xml'
          archiveArtifacts allowEmptyArchive: true, artifacts: 'test-results/**/*', fingerprint: true
        }
      }
    }

    stage('Deploy production') {
      when {
        allOf {
          branch 'main'
          not { changeRequest() }
        }
      }
      steps {
        sh 'scripts/ci/deploy.sh'
      }
    }
  }

  post {
    always {
      sh 'docker image prune -f --filter "until=168h" || true'
      deleteDir()
    }
  }
}
